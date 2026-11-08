"""验证：加了中文查询重写后，原始口语问法能否答出权重数值。

用法：python exp_after_fix.py
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
FINGERPRINTS = ["技术方案权重", "投标报价权重", "企业资信及履约能力 J2"]

client = CombineClient()
client.load_knowledge()

retriever = client.get_retrievers(DOC)
docs = retriever.invoke(QUERY)

hit = any(any(fp in d.page_content for fp in FINGERPRINTS) for d in docs)
print("=" * 72)
print(f"检索到 {len(docs)} 块，命中权重条款 = {hit}")
for d in docs:
    print(f"  p.{d.metadata.get('page')}: {d.page_content.replace(chr(10), ' ')[:90]}")
print("=" * 72)

client.clear_history()
result = client.invoke(QUERY, DOC, max_length=2000, temperature=0.2)
print("\n【回答】\n")
print(result.get("answer"))
