"""定位「权重条款检索不到」的故障层：召回不足，还是被过滤/重排砍掉？

用法：python exp_recall.py
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
QUERY = "评标办法的评分构成是什么？价格、技术、商务各占多少分？"

# 正确答案的指纹（文档 L1321-1323 那三行权重）
FINGERPRINTS = ["技术方案权重", "投标报价权重", "企业资信及履约能力 J2", "J3（取值范围"]


def has_answer(docs):
    return any(any(fp in d.page_content for fp in FINGERPRINTS) for d in docs)


client = CombineClient()
client.load_knowledge()

ensemble = client.get_ensemble(DOC)
dense, sparse = ensemble.retrievers

print("=" * 72)
print("第 1 步：原始召回（不过滤、不重排）")
print("=" * 72)

print("\n[向量检索] 加大 k 能不能捞到？")
for k in (3, 8, 20):
    dense.search_kwargs = {"k": k}
    docs = dense.invoke(QUERY)
    print(f"  k={k:<3} 命中={has_answer(docs)!s:<5} 页码={[d.metadata.get('page') for d in docs]}")

print("\n[BM25 检索] 加大 k 能不能捞到？")
for k in (3, 8, 20):
    docs = sparse.invoke(QUERY)
    print(f"  k={k:<3} 命中={has_answer(docs)!s:<5} 页码={[d.metadata.get('page') for d in docs]}")

print("\n" + "=" * 72)
print("第 2 步：完整链路（LLM 过滤 + 重排 top_n=3）")
print("=" * 72)

retriever = client.get_retrievers(DOC)
docs = retriever.invoke(QUERY)
print(f"  最终返回 {len(docs)} 块，命中={has_answer(docs)}，页码={[d.metadata.get('page') for d in docs]}")
for d in docs:
    body = d.page_content.replace("\n", " ")[:70]
    print(f"    p.{d.metadata.get('page')}: {body}")

print("\n结论提示：")
print("  - 若第 1 步命中、第 2 步不命中 → 问题在过滤/重排（top_n 太小或过滤器误杀）")
print("  - 若第 1 步就不命中 → 问题在切分/嵌入/查询表达（更深层）")
