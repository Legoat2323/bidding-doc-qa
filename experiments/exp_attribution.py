"""对 19 题答案跑条款级归因校验，统计 OK / NO_SOURCE / MISMATCH。

用法：python experiments/exp_attribution.py
数据来源：experiments/selfcheck_dump.json（19 题答案）
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_ROOT)
sys.path.insert(0, _ROOT)

from attribution import normalize, verify_answer

raw = open("bid_fulltext.txt", encoding="utf-8").read()
full_norm, orig = normalize(raw)
rows = json.load(open("experiments/selfcheck_dump.json", encoding="utf-8"))

tot = {"OK": 0, "NO_SOURCE": 0, "MISMATCH": 0}
suspects = []

for r in rows:
    res = verify_answer(r["answer"], full_norm, orig)
    for x in res:
        tot[x["verdict"]] += 1
    bad = [x for x in res if x["verdict"] != "OK"]
    if bad:
        suspects.append((r["no"], r["q"], bad))

print(f"共 {len(rows)} 题，断言总数 {sum(tot.values())}")
print(f"  OK        {tot['OK']}")
print(f"  NO_SOURCE {tot['NO_SOURCE']}")
print(f"  MISMATCH  {tot['MISMATCH']}")
print()

for no, q, bad in suspects:
    print(f"【第 {no} 题】{q}")
    for x in bad:
        print(f"  [{x['verdict']}] {x['claim'][:70]}")
        if x["verdict"] == "MISMATCH" and x["seg"]:
            print(f"      出处：{x['seg'][:200]}")
    print()
