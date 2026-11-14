import os, sys, time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
os.chdir(_ROOT)
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT.parent / "libs"))

from dotenv import load_dotenv
load_dotenv()

from combine_client import CombineClient

DOC = "招标文件正文22.pdf"

QUESTIONS = [
    "投标担保的金额是多少？",
    "类似工程业绩的考核期限是多久？",
    "最高投标限价是多少？",
    "总工期多少天？",
    "投标有效期是多久？",
    "质量保证金的比例是多少？",
    "评标委员会由几个人组成？",
    "投标文件用什么字体？",
]
REPEAT = 3      # 每题跑 3 次，共 24 次

client = CombineClient()
client.load_knowledge()

# 热身一次，结果丢掉
client.clear_history()
t0 = time.perf_counter()
client.invoke(QUESTIONS[0], DOC, max_length=50, temperature=0.0)
print(f"热身 {time.perf_counter() - t0:.2f}s")

rows = []
for q in QUESTIONS:
    for _ in range(REPEAT):
        client.clear_history()          # 清历史，避免上一题拖慢这题
        t0 = time.perf_counter()
        client.invoke(q, DOC, max_length=1500, temperature=0.1)
        rows.append(time.perf_counter() - t0)


def pct(xs, p):
    xs = sorted(xs)
    i = min(len(xs) - 1, max(0, round((p / 100) * (len(xs) - 1))))
    return xs[i]

print()
print(f"样本数 {len(rows)}")
print(f"平均  {sum(rows)/len(rows):.2f}s")
print(f"P50   {pct(rows, 50):.2f}s")
print(f"P95   {pct(rows, 95):.2f}s")
print(f"最慢  {max(rows):.2f}s   最快 {min(rows):.2f}s")























