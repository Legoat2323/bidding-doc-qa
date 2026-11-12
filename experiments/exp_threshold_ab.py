"""阈值到底有没有用：A/B/C 三组对照实验。

为什么之前那个 A/B 看不出效果：
    12 道题全是"文档里有答案"的题，模型靠 prompt 本来就会答对；
    阈值唯一的用处是拦住"文档里根本没有的东西"，而评估集里一道这样的题都没有。
    没有反例，就测不出效果。

所以这里分两组：
    A 组（有答案）：阈值不能把它们弄坏 —— 看"答对率"
    B 组（文档里没有）：阈值应该让它们答"未提及" —— 看"拒答率"

怎么判断阈值有效：
    B 组拒答率上升，同时 A 组答对率不下降。

用法：
    python experiments/exp_threshold_ab.py            # 默认扫 0 / 0.2 / 0.3
    python experiments/exp_threshold_ab.py 0 0.25 0.5
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
sys.path.insert(0, ROOT)

LIBS = os.path.join(os.path.dirname(ROOT), "libs")
if os.path.isdir(LIBS) and LIBS not in sys.path:
    sys.path.insert(0, LIBS)

from dotenv import load_dotenv

load_dotenv()

from loguru import logger

logger.remove()

from config.settings import settings
from combine_client import CombineClient

DOC = settings.bid_doc

# 文档里有答案的题：答对 = 出现正确关键词
A_GROUP = [
    ("总工期多少天？", ["360"]),
    ("投标有效期是多久？", ["90"]),
    ("设计费多少？", ["2336570", "233"]),
    ("暂列金额是多少？", ["15772346", "1577"]),
    ("最高投标限价是多少？", ["150627581", "150,627", "1.5亿", "15062"]),
]

# 文档里没有的题：答对 = 说"未提及"，而不是编一个答案
B_GROUP = [
    "今天桂林天气怎么样？",
    "投标人的股票代码是多少？",
    "项目经理的手机号码是多少？",
]

NO_ANSWER_WORDS = ("未提及", "没有", "未找到", "无法", "不含", "未说明", "不详")


def ask(client, question):
    result = client.invoke(question, DOC, max_length=1500, temperature=0.1)
    return (result.get("answer") or "").strip(), result.get("context") or []


def main():
    thresholds = [float(x) for x in sys.argv[1:]] or [0.0, 0.2, 0.3]

    print("加载知识库 ...")
    client = CombineClient()
    client.load_knowledge()

    print(f"\n{'阈值':<8}{'A组答对':<12}{'B组拒答':<12}{'平均片段'}")
    print("-" * 56)

    for t in thresholds:
        # settings 是 frozen dataclass，实验里临时改一下（不影响正常启动）
        object.__setattr__(settings, "relevance_threshold", t)

        a_ok = 0
        for question, keys in A_GROUP:
            client.clear_history()
            answer, docs = ask(client, question)
            if any(k in answer for k in keys):
                a_ok += 1

        b_ok = 0
        ctx_sizes = []
        for question in B_GROUP:
            client.clear_history()
            answer, docs = ask(client, question)
            ctx_sizes.append(len(docs))
            if any(w in answer for w in NO_ANSWER_WORDS):
                b_ok += 1

        for question, _ in A_GROUP:
            pass

        print(f"{t:<8.2f}{a_ok}/{len(A_GROUP):<10}{b_ok}/{len(B_GROUP):<10}"
              f"{sum(ctx_sizes) / len(ctx_sizes):.1f}")

    print("\n怎么读：")
    print("  · A 组掉了 → 阈值太高，把有答案的题也拒了（不能接受）")
    print("  · B 组上去了 → 阈值起作用了，模型不再硬编")
    print("  · 有效 = B 组上升 且 A 组不下降")


if __name__ == "__main__":
    main()
