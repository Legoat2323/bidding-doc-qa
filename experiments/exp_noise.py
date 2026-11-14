# -*- coding: utf-8 -*-
"""「履约担保的比例」这题：带噪声的查询 vs 干净的查询，检索结果差多少？

背景：改 prompt 之前，改写会把「履约担保 比例」扩成
      「履约担保 比例 权重 取值范围 计分」。
      那两个评分词到底有没有把正确答案挤下去？这里只测 BM25 一路，看得最清楚。

用法（在 courses\\docqa 下）：
    .\\run_exp.cmd experiments\\exp_noise.py
"""
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_ROOT)
sys.path.insert(0, os.path.join(os.path.dirname(_ROOT), "libs"))
sys.path.insert(0, _ROOT)

from dotenv import load_dotenv

load_dotenv()

from loguru import logger

logger.remove()

from langchain_community.retrievers import BM25Retriever

from custom_loader import MyCustomLoader
from knowledge import bigram_tokenize

DOC = os.path.join("示例文档", "招标文件正文22.pdf")

# 判断「命中正确答案」的标准：片段里同时有 履约担保 和 10%
def is_answer(text: str) -> bool:
    return "履约担保" in text and ("10%" in text or "10 %" in text)


QUERIES = [
    ("改之前（带评分噪声）", "履约担保 比例 权重 取值范围 计分"),
    ("改之后（干净）", "履约担保 比例"),
    ("改造后的原始问句", "中标后履约担保的比例是多少"),
]

documents = MyCustomLoader(DOC).load()
print(f"切片总数 {len(documents)}")

for name, q in QUERIES:
    retriever = BM25Retriever.from_documents(
        documents, k=10, preprocess_func=bigram_tokenize
    )
    hits = retriever.invoke(q)
    rank = next((i + 1 for i, d in enumerate(hits) if is_answer(d.page_content)), None)
    print()
    print("=" * 78)
    print(f"{name}：{q!r}")
    print(f"正确答案所在排名：{rank if rank else '前 10 没出现'}")
    for i, d in enumerate(hits[:3], 1):
        page = d.metadata.get("page", "?")
        snippet = re.sub(r"\s+", " ", d.page_content)[:52]
        flag = "★" if is_answer(d.page_content) else " "
        print(f"  {flag} #{i} (p.{page}) {snippet}")
