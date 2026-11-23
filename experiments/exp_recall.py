"""诊断：评标委员会那道，到底卡在「召回」还是「重排」。

做法：
    1. 先把答案切片找出来（含「9 人或以上单数」的那片）
    2. 召回扩到 k=32，分别看向量 / BM25(2-gram) / 融合，答案切片在不在候选里、排第几
    3. 再对这 32 条做 rerank，看它排到第几

判定：
    ① 32 条里没有            → 召回不行
    ② 32 条里有，rerank 后排 5 名外 → 重排不行
    ③ rerank 后排进前 5     → 链路配置和线上不一致，得查
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_ROOT)
sys.path.insert(0, _ROOT)
_LIBS = os.path.join(os.path.dirname(_ROOT), "libs")
if os.path.isdir(_LIBS) and _LIBS not in sys.path:
    sys.path.insert(0, _LIBS)

from dotenv import load_dotenv

load_dotenv()

from loguru import logger

logger.remove()
logger.add(sys.stderr, level="ERROR")

from combine_client import CombineClient
from custom_loader import MyCustomLoader
from knowledge import bigram_tokenize
from models import get_ali_rerank
from langchain_community.retrievers import BM25Retriever
from langchain.retrievers import EnsembleRetriever    #这个是混合检索

DOC = "招标文件正文22.pdf"
DOC_PATH = os.path.join("示例文档", DOC)
K = 32

QUERY = "评标委员会由几个人组成？"
NEEDLES = ["9 人或以上单数", "9人或以上单数", "九人"]


def rank_of(docs, targets):
    for i, d in enumerate(docs):
        if d.page_content in targets:
            return i + 1
    return 0


def main() -> None:
    print("加载知识库 ...")
    client = CombineClient()
    client.load_knowledge()

    documents = MyCustomLoader(DOC_PATH).load()
    print(f"切片总数：{len(documents)}")

    targets = {d.page_content for d in documents
               if any(n in d.page_content for n in NEEDLES)}
    print(f"含答案的切片：{len(targets)} 条")    #这个是按关键词判定
    if not targets:
        print("⚠ 没有切片含答案，先回去查切片")
        return

    # ---- 1. 向量召回 k=32 ----
    ensemble = client.get_ensemble(DOC)
    vec = ensemble.retrievers[0]
    vec.search_kwargs["k"] = K
    vec_docs = vec.invoke(QUERY)
    print(f"\n向量 k={K}：{len(vec_docs)} 条，答案切片排名 = {rank_of(vec_docs, targets) or '不在候选里'}")

    # ---- 2. BM25(2-gram) 召回 k=32 ----
    bm25 = BM25Retriever.from_documents(documents, k=K, preprocess_func=bigram_tokenize)   #preprocess_func=bigram_tokenize中文分词
    bm_docs = bm25.invoke(QUERY)
    print(f"BM25 k={K}：{len(bm_docs)} 条，答案切片排名 = {rank_of(bm_docs, targets) or '不在候选里'}")  #rank_of(bm_docs, targets)答案切片在检索回来的片段里地排名

    # ---- 3. 融合 k=64 ----      最大情况是64 有重复的就可以合并
    ens = EnsembleRetriever(retrievers=[vec, bm25], weights=[0.5, 0.5])
    ens_docs = ens.invoke(QUERY)
    print(f"融合 k={K}：{len(ens_docs)} 条，答案切片排名 = {rank_of(ens_docs, targets) or '不在候选里'}")

    # ---- 4. rerank  融合之后的 ----
    print("\n对 32 条候选做 rerank（这一步要调 API，慢一点）...")
    reranked = get_ali_rerank(top_n=K).compress_documents(ens_docs, QUERY)
    r = rank_of(reranked, targets)
    print(f"rerank 后：{len(reranked)} 条，答案切片排名 = {r or '不在候选里'}")

    print("\n" + "=" * 74)
    print("【结论】")
    print("=" * 74)
    if r and r <= 5:
        print("  rerank 后进了前 5 → 线上链路和这里的配置不一致，回去查 bid_eval 的 ask()")
    elif r:
        print(f"  rerank 后有，但排第 {r} → 卡在重排：候选够了，重排序没把它顶上来")
    elif rank_of(ens_docs, targets):
        print("  融合候选里有、rerank 后没了 → 重排序把它丢了")
    else:
        print("  32 条候选里都没有 → 卡在召回：要么扩得更大，要么改查询")


if __name__ == "__main__":
    main()
