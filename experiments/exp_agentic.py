"""跑 23 题开发集，看“让模型自己决定要不要检索”会变成什么样。

比较对象是 L1（bid_eval.py）：同一批题、同一份知识库，区别只在
    L1    —— 每题固定检索一次，k=5，然后生成；
    这里  —— 模型自己决定调 0/1/2 次 search_tender。
"""
import json, os, sys, time
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_ROOT); sys.path.insert(0, _ROOT)
_LIBS = os.path.join(os.path.dirname(_ROOT), "libs")
if os.path.isdir(_LIBS) and _LIBS not in sys.path: sys.path.insert(0, _LIBS)
from dotenv import load_dotenv; load_dotenv()
from loguru import logger; logger.remove(); logger.add(sys.stderr, level="ERROR")

import bid_eval as ev
from agent import run_agent

rows = []

def run_one(q, kws, is_refusal=False):
    s = time.time()
    ans, used, trace = run_agent(q)
    secs = round(time.time() - s, 1)
    if is_refusal:
        ok = any(w in (ans or "") for w in ev.NO_ANSWER_WORDS)
    else:
        ok = bool(ev.hit_any(ans or "", kws))
    rows.append({"q": q, "grp": "B" if is_refusal else "A", "used": used,
                 "ok": ok, "secs": secs, "trace": trace,
                 "answer": (ans or "")[:200]})
    mark = "OK " if ok else "BAD"
    qs = [t["query"] for t in trace]
    tag = "B" if is_refusal else "A"
    print(f"[{tag}] {mark} {used}次 {secs}s  {q}  {qs}")

for q, kws, is_t in ev.CASES:
    run_one(q, kws)
for q in ev.REFUSAL_CASES:
    run_one(q, None, is_refusal=True)

n_a, n_b = len(ev.CASES), len(ev.REFUSAL_CASES)
a_ok = sum(r["ok"] for r in rows if r["grp"] == "A")
b_ok = sum(r["ok"] for r in rows if r["grp"] == "B")
no_tool = sum(1 for r in rows if r["used"] == 0)
avg = sum(r["secs"] for r in rows) / len(rows)
total_calls = sum(r["used"] for r in rows)
print()
print(f"A 回答 {a_ok}/{n_a}   B 拒答 {b_ok}/{n_b}   综合 {a_ok+b_ok}/{n_a+n_b}   （L1 是 23/23）")
print(f"主动不检索 {no_tool}/{len(rows)} 题；工具调用总数 {total_calls}；平均 {avg:.1f}s/题（L1 P95 3.17s）")
with open(os.path.join("experiments", "agentic_dump.json"), "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=2)
