"""切片实验：为什么「评标委员会由几个人组成」检索不到答案所在的切片。

背景：
    原文第 20 页写着「评标委员会成员人数为 9 人或以上单数」，
    切片里也确实有这句话（bid_eval 里人工确认过），
    但检索得到的 top-5 里就是没有它 → 检索 ❌。

这个脚本分四步看：
    1. 答案所在的切片长什么样（长度、混了哪些条款）
    2. BM25（默认分词）单独查，能不能捞到
    3. BM25（2-gram 分词）单独查，能不能捞到
    4. 向量单独查、融合后，能不能捞到

用法：run_exp.cmd experiments\exp_slice.py
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
from langchain_community.retrievers import BM25Retriever

DOC = "招标文件正文22.pdf"
DOC_PATH = os.path.join("示例文档", DOC)   # 原文实际位置
QUERY = "评标委员会由几个人组成？"
NEEDLES = ("单数", "9 人", "9人", "九人")


def show(title, rank, total, doc):
    """打印一条：能不能捞到 + 排名 + 开头几十个字。"""
    mark = f"命中 第 {rank} 位" if rank else "没捞到"
    print(f"  {title:<28} {mark:<12} [{total} 条] {doc[:60].replace(chr(10), ' ')}")


def find_hits(docs, needles=NEEDLES):
    return [(i + 1, d) for i, d in enumerate(docs) if any(n in d.page_content for n in needles)]


def main() -> None:
    print("加载知识库 ...")
    client = CombineClient()
    client.load_knowledge()

    print("重新切分原文（和建索引时同一套参数）...")
    documents = MyCustomLoader(DOC_PATH).load()
    print(f"切片总数：{len(documents)}\n")

    # ---------- 第 1 步：答案所在的切片 ----------
    print("=" * 92)
    print("【第 1 步】原文里哪些切片含「9 人或以上单数」")
    print("=" * 92)
    targets = find_hits(documents)
    if not targets:
        print("  ⚠ 没有任何切片包含答案关键词，先检查原文抽取是不是丢了这句")
    for i, d in targets:
        text = d.page_content.replace("\n", " ")
        print(f"  切片 #{i}  长度 {len(d.page_content)} 字  page={d.metadata.get('page', '?')}")
        print(f"  开头：{text[:120]}")
        print(f"  结尾：{text[-120:]}")
        print()

    if not targets:
        return

    target_texts = {d.page_content for _, d in targets}

    def rank_of(docs):
        for i, d in enumerate(docs):
            if d.page_content in target_texts:
                return i + 1
        return 0

    # ---------- 第 2 步：BM25 默认分词 ----------
    print("=" * 92)
    print("【第 2 步】BM25 单路（默认 text.split，中文整句一个词）")
    print("=" * 92)
    bm25_default = BM25Retriever.from_documents(documents, k=8)
    got = bm25_default.invoke(QUERY)
    r = rank_of(got)
    show("BM25 默认分词", r, len(got), got[0].page_content if got else "")
    if not r:
        print(f"  → top-8 里没有答案切片，第一条是：{got[0].page_content[:60]}")

    # ---------- 第 3 步：BM25 2-gram ----------
    print()
    print("=" * 92)
    print("【第 3 步】BM25 单路（2-gram 分词）")
    print("=" * 92)
    bm25_bigram = BM25Retriever.from_documents(documents, k=8, preprocess_func=bigram_tokenize)
    got = bm25_bigram.invoke(QUERY)
    r = rank_of(got)
    show("BM25 2-gram", r, len(got), got[0].page_content if got else "")
    if not r:
        print(f"  → top-8 里还是没有，第一条是：{got[0].page_content[:60]}")

    # ---------- 第 4 步：向量 / 融合 ----------
    print()
    print("=" * 92)
    print("【第 4 步】向量单路 / 融合后（就是线上实际用的那条路）")
    print("=" * 92)
    ensemble = client.get_ensemble(DOC)
    vec_retriever = ensemble.retrievers[0]
    got_vec = vec_retriever.invoke(QUERY)
    show("向量", rank_of(got_vec), len(got_vec), got_vec[0].page_content if got_vec else "")

    got_ens = ensemble.invoke(QUERY)
    show("融合（向量+BM25）", rank_of(got_ens), len(got_ens), got_ens[0].page_content if got_ens else "")

    print()
    print("=" * 92)
    print("【结论提示】")
    print("=" * 92)
    print("  · 单路都捞得到、融合后丢了 → RRF 融合的锅（它只看排名，不看分数）")
    print("  · 单路都捞不到 → 切片本身的锅（内容被稀释/切成两半）")
    print("  · 只有 2-gram 捞得到 → 中文分词是瓶颈")


if __name__ == "__main__":
    main()
