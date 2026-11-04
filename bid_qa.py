"""招投标文件问答：三个真实业务问题的最小验证版。

跑通后再接界面。用法（docqa 目录下，PYTHONPATH 指向 courses\\libs）：
    python bid_qa.py
"""
import os
import shutil
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv()  # 读 .env 里的 DASHSCOPE_API_KEY

# 把日志压到 WARNING，否则 DEBUG 会把结果刷没
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="WARNING")

DOC = "招标文件正文22.pdf"
SRC = os.path.join("示例文档", DOC)
DST = os.path.join("chroma", "knowledge", DOC)

if not os.path.exists(DST):
    os.makedirs(os.path.dirname(DST), exist_ok=True)
    shutil.copy(SRC, DST)
    print(f"已复制到知识库: {DST}")
else:
    print(f"知识库中已存在: {DST}")

from combine_client import CombineClient

client = CombineClient()
print("\n正在建索引（首次会调用嵌入接口，332 页需要一两分钟）...")
client.load_knowledge()

# 三个「投标决策」真正会问的问题
QUESTIONS = [
    "投标人需要具备哪些资格要求？包括资质等级、业绩、财务和人员要求。",
    "哪些情形会被否决投标（即废标）？",
    "评标办法的评分构成是什么？价格、技术、商务各占多少分？",
]

for i, q in enumerate(QUESTIONS, 1):
    client.clear_history()          # 每题独立，避免历史互相干扰
    print("\n" + "=" * 70)
    print(f"【问题 {i}】{q}")
    print("=" * 70)

    result = client.invoke(q, DOC, max_length=4000, temperature=0.2)
    ctx = result.get("context", [])
    print(f"\n检索到 {len(ctx)} 个片段，来源页：")
    for j, d in enumerate(ctx, 1):
        page = d.metadata.get("page", "?")
        preview = d.page_content.replace("\n", " ")[:100]
        print(f"  [{j}] p.{page}  {preview}")

    print(f"\n【回答】\n{result.get('answer')}")
