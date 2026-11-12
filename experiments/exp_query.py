"""验证「用户用词 ≠ 文档用词」是否导致检索失败。

对同一意图用三种问法，看哪种能召回权重条款。
用法：python exp_query.py
"""
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv

load_dotenv()

from loguru import logger

logger.remove()
logger.add(sys.stderr, level="WARNING")

from combine_client import CombineClient
from knowledge import get_md5

DOC = "招标文件正文22.pdf"
FINGERPRINTS = ["技术方案权重", "投标报价权重", "企业资信及履约能力 J2", "J3（取值范围"]

QUERIES = {
    "A 原始问法": "评标办法的评分构成是什么？价格、技术、商务各占多少分？",
    "B 术语对齐": "技术方案权重 J1、企业资信及履约能力权重 J2、投标报价权重 J3 分别是多少？",
    "C 纯关键词": "J1 J2 J3 权重 取值范围",
}

client = CombineClient()
client.load_knowledge()

ensemble = client.get_ensemble(DOC)
dense, sparse = ensemble.retrievers
dense.search_kwargs = {"k": 8}


def hit(docs):
    return any(any(fp in d.page_content for fp in FINGERPRINTS) for d in docs)


for name, q in QUERIES.items():
    print("=" * 72)
    print(f"{name}: {q}")
    print("=" * 72)

    v = dense.invoke(q)
    print(f"  向量 k=8  命中={hit(v)!s:<6} 页码={[d.metadata.get('page') for d in v]}")

    b = sparse.invoke(q)
    print(f"  BM25      命中={hit(b)!s:<6} 页码={[d.metadata.get('page') for d in b]}")

    if hit(v) or hit(b):
        for d in (v + b):
            if any(fp in d.page_content for fp in FINGERPRINTS):
                print(f"    >>> 命中片段 (p.{d.metadata.get('page')}): "
                      f"{d.page_content.replace(chr(10), ' ')[:120]}")
                break
    print()
