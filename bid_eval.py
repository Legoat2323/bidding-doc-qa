"""招投标问答效果评估：12 个问题，分别看检索和回答。

指标：
    检索命中 —— top-5 片段里有没有含正确答案的
    回答命中 —— 最终回答里有没有

这两者要分开看：
    检索 ❌ → 数据/切分/检索策略的问题
    检索 ✅ 但回答 ❌ → 模型没用好上下文（prompt 的问题）

用法：python bid_eval.py
"""
import os
import re
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(_ROOT)
sys.path.insert(0, _ROOT)

# 这个项目的依赖是 vendored 在 courses\libs 里的（run.ps1 也是这么设的）。
# 自己加进 sys.path，PyCharm 直接点 Run 也能跑，不用手动配 PYTHONPATH。
_LIBS = os.path.join(os.path.dirname(_ROOT), "libs")
if os.path.isdir(_LIBS) and _LIBS not in sys.path:
    sys.path.insert(0, _LIBS)

from dotenv import load_dotenv

load_dotenv()

from loguru import logger

logger.remove()
logger.add(sys.stderr, level="WARNING")

from combine_client import CombineClient
from knowledge import get_md5
from models import get_ali_rerank, get_lc_model_client

DOC = "招标文件正文22.pdf"
NO_DATA_MARK = ("未提及", "没有", "未找到", "不含")

# 模板问题的检索式（和 bid_app.py 里保持一致）
RETRIEVAL_QUERY = {
    "评分构成 / 权重": "权值构成 J1 J2 J3 技术方案权重 企业资信及履约能力 投标报价权重",
    "否决投标情形": "否决投标的情形 附件2-2 无效投标",
    "资格要求": "投标人资格要求 资质等级 类似工程业绩",
    "投标保证金": "投标保证金 金额 形式 退还 3.4.1",
}

# ---- A 组：文档里有答案的题（期望关键词，任一命中即算对）----
# (问题, 期望关键词组, 是否走模板检索)
CASES = [
    # 模板类
    ("评分构成 / 权重", ["0.25", "0.40", "0.35"], True),
    ("否决投标情形", ["否决", "取消", "无效", "不予"], True),
    ("资格要求", ["6750", "资质"], True),
    ("投标保证金", ["保证金", "投标担保", "担保"], True),
    # 自由提问（走完整 RAG）
    ("投标有效期是多久？", ["90"], False),
    ("总工期多少天？", ["360"], False),
    ("最高投标限价是多少？", ["150627581", "150,627", "1.5亿", "15062"], False),
    ("设计费多少？", ["2336570", "233"], False),
    ("暂列金额是多少？", ["15772346", "1577"], False),
    ("质量保证金的比例是多少？", ["3%"], False),
    ("投标文件用什么字体？", ["仿宋", "4 号"], False),
    # 2026-11-12 新增 8 题（答案已对照原文核对）
    ("投标截止时间是什么时候？", ["2023-12-20", "2023 年 12 月 20", "09:00"], False),
    ("投标文件需要提交几份？", ["一份", "1份", "1 份"], False),
    ("评标委员会由几个人组成？", ["9 人", "9人", "九人"], False),
    ("评标专家从哪里抽取？", ["专家库", "随机抽取"], False),
    ("基准日期是怎么确定的？", ["28"], False),
    ("技术方案采用什么评审方式？", ["暗标"], False),
    ("未中标的投标担保什么时候退还？", ["5 个工作日", "5个工作日", "5 个"], False),
    ("履约保证金什么情况下不予退还？", ["不履行合同", "不予退还"], False),
]

# ---- B 组：文档里没有答案的题（只有答"未提及"才算对）----
# 为什么单独一组：这类题没有"期望关键词"可言，检索命中率也不该把它算进分母。
# 它们存在，是为了测"模型会不会硬编" —— 这是 RAG 最容易翻车的地方。
REFUSAL_CASES = [
    "项目经理需要什么证书？",
    "投标文件需要提交几份纸质正本和副本？",
    "项目经理的年龄上限是多少？",
    "项目经理需要提供几年的社保缴纳证明？",
]

NO_ANSWER_WORDS = ("未提及", "没有", "未找到", "不含", "未说明", "无法")

print("加载知识库 ...")
client = CombineClient()
client.load_knowledge()
ensemble = client.get_ensemble(DOC)
rerank = get_ali_rerank(top_n=5)
llm = get_lc_model_client(temperature=0.1, max_tokens=1500)


def hit_any(text, keywords):
    return any(k in (text or "") for k in keywords)


def ctx_of(docs):
    return "\n".join(f"[p.{d.metadata.get('page','?')}] {d.page_content}" for d in docs)


PROMPT = """你是招投标文件助手。只根据下面的【原文片段】回答问题。

要求：
1. 只写片段里有的内容
2. 每条结论后用 (p.页码) 标出来源
3. 片段里没有的，回答"文件中未提及"
4. 不要写开场白
5. 如果是列举某类情形（如否决投标、废标），先说清后果，例如：以下情形将导致投标被否决

【原文片段】
{context}

【问题】
{question}
"""


def ask(q, is_template):
    if is_template:
        query = RETRIEVAL_QUERY[q]
        docs = rerank.compress_documents(ensemble.invoke(query), query)
        answer = llm.invoke(PROMPT.format(context=ctx_of(docs),
                                          question=q.replace(" / ", "、"))).content
    else:
        client.clear_history()
        result = client.invoke(q, DOC, max_length=1500, temperature=0.1)
        docs = result.get("context", [])
        answer = result.get("answer") or ""
    return docs, answer


ret_ok = ans_ok = 0
rows = []

for q, keys, is_template in CASES:
    docs, answer = ask(q, is_template)
    r = hit_any(ctx_of(docs), keys)
    a = hit_any(answer, keys)
    ret_ok += r
    ans_ok += a
    rows.append((q, "✅" if r else "❌", "✅" if a else "❌", answer.replace("\n", " ")[:60]))

refuse_ok = 0
refuse_rows = []
for q in REFUSAL_CASES:
    docs, answer = ask(q, False)
    ok = hit_any(answer, NO_ANSWER_WORDS)
    refuse_ok += ok
    refuse_rows.append((q, "✅" if ok else "❌", answer.replace("\n", " ")[:60]))

W = 30
print()
print("=" * 96)
print("【A 组】文档里有答案：检索和回答都该命中")
print("=" * 96)
print(f"{'问题':<{W}}{'检索':<6}{'回答':<6}片段回答")
print("-" * 96)
for q, r, a, preview in rows:
    print(f"{q:<{W}}{r:<6}{a:<6}{preview}")

print()
print("=" * 96)
print("【B 组】文档里没有答案：回答必须是「未提及」，硬编就是错")
print("=" * 96)
for q, ok, preview in refuse_rows:
    print(f"{q:<{W}}{ok:<6}{preview}")

n = len(CASES)
m = len(REFUSAL_CASES)
print("=" * 96)
print(f"A 组检索命中率：{ret_ok}/{n} = {ret_ok/n:.0%}   （分母只含有答案的题）")
print(f"A 组回答命中率：{ans_ok}/{n} = {ans_ok/n:.0%}")
print(f"B 组拒答正确率：{refuse_ok}/{m} = {refuse_ok/m:.0%}   （该说「未提及」时说了没有）")
print(f"综合回答正确率：{ans_ok + refuse_ok}/{n + m} = {(ans_ok + refuse_ok)/(n + m):.0%}")
