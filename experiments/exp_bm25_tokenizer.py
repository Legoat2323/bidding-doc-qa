"""实验：BM25 的中文分词问题。

背景：
    评估集里「评标委员会由几个人组成？」和「评标专家从哪里抽取？」两道题检索失败，
    但原文 p.20 明明写着"评标委员会构成：9 人或以上单数""从湖南省综合评标专家库中随机抽取"。

排查结论：
    1. 原文提取没问题（p.20 文本完整）
    2. 切片里有这句话（切片 #65，468 字）
    3. 但 16 条候选里召不回它 —— 问题出在召回

假设：LangChain 的 BM25Retriever 默认用 text.split() 分词。
     中文句子没有空格，整句变成一个 token → BM25 等于没分词 → 关键词匹配失效。

验证：同一批切片，分别用「默认分词」和「2-gram 切分」建 BM25，看含答案的切片排第几。

用法：python experiments/exp_bm25_tokenizer.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
sys.path.insert(0, ROOT)

LIBS = os.path.join(os.path.dirname(ROOT), "libs")
if os.path.isdir(LIBS) and LIBS not in sys.path:
    sys.path.insert(0, LIBS)

from custom_loader import MyCustomLoader
from langchain_community.retrievers import BM25Retriever

from config.settings import settings

PDF = os.path.join("示例文档", settings.bid_doc)

# 两处答案所在的切片里一定有的字符串
KEYS = ("评标委员会构成", "评标专家确定方式")
QUERIES = [
    "评标委员会由几个人组成？",
    "评标专家从哪里抽取？",
    "评标委员会构成",          # 用原文措辞，作为对照组
]


def bigram(text: str):
    """中文用相邻两字切分：评标委员会 -> 评标/标委/委员/员会"""
    text = re.sub(r"\s+", "", text)
    return [text[i:i + 2] for i in range(len(text) - 1)]


def build(func):
    docs = MyCustomLoader(PDF).load()
    if func is None:
        return BM25Retriever.from_documents(docs, k=8)
    return BM25Retriever.from_documents(docs, k=8, preprocess_func=func)


def run(name, func):
    bm25 = build(func)
    print(f"\n===== {name} =====")
    for q in QUERIES:
        got = bm25.invoke(q)
        pos = [i for i, d in enumerate(got) if any(k in d.page_content for k in KEYS)]
        print(f"  {q:<18} 召回 {len(got)} 条，含答案排第 {pos if pos else '没有'}")


if __name__ == "__main__":
    print("加载切片 ...")
    run("默认分词（text.split()）", None)
    run("2-gram 切分", bigram)
    print("\n结论：如果 2-gram 明显更好，说明 BM25 之前等于没分词。")
