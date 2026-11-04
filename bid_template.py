"""业务模板检索：对高频问题预先写好检索式，绕过"口语 → 文档术语"的鸿沟。

这是真实的工程做法：
    招投标场景里，用户真正会问的问题就那几十个（资质、否决、评分、保证金、工期…）。
    与其指望一个通用链路搞定所有问法，不如把高频问题做成模板，
    每个模板配一个「贴文档用词」的检索式。命中率立刻从 0 到 1。

用法：python bid_template.py
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
from models import get_ali_rerank

DOC = "招标文件正文22.pdf"

# (用户会怎么问, 实际发给检索器的查询)
TEMPLATES = [
    ("评分构成 / 权重", "权值构成 J1 J2 J3 技术方案权重 企业资信及履约能力 投标报价权重"),
    ("否决投标情形", "否决投标的情形 附件2-2 无效投标"),
    ("资格要求", "投标人资格要求 资质等级 类似工程业绩"),
    ("投标保证金", "投标保证金 金额 形式 退还 3.4.1"),
]

FINGERPRINT = {
    "评分构成 / 权重": ["技术方案权重", "投标报价权重"],
    "否决投标情形": ["否决投标的情形"],
    "资格要求": ["资格要求", "资质"],
    "投标保证金": ["投标保证金"],
}

client = CombineClient()
client.load_knowledge()

ensemble = client._MyKnowledge__retrievers[get_md5(DOC)]
rerank = get_ali_rerank(top_n=5)

print("=" * 72)
print("业务模板检索测试")
print("=" * 72)

for label, query in TEMPLATES:
    candidates = ensemble.invoke(query)
    docs = rerank.compress_documents(candidates, query)
    fps = FINGERPRINT[label]
    hit = any(any(fp in d.page_content for fp in fps) for d in docs)

    print(f"\n【{label}】")
    print(f"  检索式: {query}")
    print(f"  候选 {len(candidates)} → 精排 {len(docs)}，命中关键条款 = {hit}")
    for d in docs[:3]:
        body = d.page_content.replace("\n", " ")[:80]
        print(f"    p.{d.metadata.get('page')}: {body}")

# 针对评分构成，把权重数值抠出来给用户看
print("\n" + "=" * 72)
print("把权重数值抠出来（这才是用户要的答案）")
print("=" * 72)
candidates = ensemble.invoke(TEMPLATES[0][1])
docs = rerank.compress_documents(candidates, TEMPLATES[0][1])

import re

for d in docs:
    text = d.page_content.replace("\n", " ")
    for m in re.finditer(r"(技术方案权重|企业资信及履约能力|投标报价权重)\s*[Jj]?\s*([123])?[（(]([^)）]*)[)）]\s*[:：]\s*([0-9.]+)", text):
        print(f"  {m.group(1)} J{m.group(2)}  取值范围 {m.group(3)}  →  **{m.group(4)}**")
