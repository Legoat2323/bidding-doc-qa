"""D1 忠实度评估：把每题的回答 + 依据片段 dump 出来，交给人判。

忠实度 ≠ 检索命中：
    检索命中问的是"资料里有没有这段"，
    忠实度问的是"回答里的每句话，是不是都能在依据片段里找到"。

用法：
    python experiments/exp_faith.py            # 只跑前 5 题
    python experiments/exp_faith.py 19         # 跑前 19 题
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_ROOT)
sys.path.insert(0, _ROOT)
_LIBS = os.path.join(os.path.dirname(_ROOT), "libs")
if os.path.isdir(_LIBS) and _LIBS not in sys.path:
    sys.path.insert(0, _LIBS)

from dotenv import load_dotenv
load_dotenv()

import bid_eval                      # 复用它的 ask / CASES（会顺带初始化检索链路）

limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5
rows = []

for i, (q, keys, is_template) in enumerate(bid_eval.CASES[:limit], 1):
    docs, answer = bid_eval.ask(q, is_template)
    pages = []
    for d in docs:
        p = d.metadata.get("page", "?")
        txt = d.page_content.replace("\n", " ")
        pages.append({"page": p, "text": txt[:220]})
    rows.append({"no": i, "q": q, "answer": answer, "pages": pages})
    print(f"[{i}] {q}\n    答：{answer[:80]}\n    依据页：{[x['page'] for x in pages]}\n")

out = os.path.join(_ROOT, "experiments", "faith_dump.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=2)
print(f"\n已写入 {out}（{len(rows)} 题）")
