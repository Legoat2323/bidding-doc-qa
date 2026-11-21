"""只测检索层：不生成答案，看 5 段里有没有关键词。
用法：python experiments/eval_retrieval.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv

load_dotenv(".env")
from loguru import logger

logger.remove()

import bid_eval as ev

rows = []
t0 = time.time()
for q, keys, is_template in ev.CASES:
    docs = ev.retrieve(q, is_template)
    ctx = ev.ctx_of(docs)
    ok = ev.hit_any(ctx, keys)
    # 关键词命中在第几段（越小越好）
    rank = next((i + 1 for i, d in enumerate(docs) if ev.hit_any(d.page_content, keys)), 0)
    rows.append((q, ok, rank, len(docs)))

cost = time.time() - t0
hit = sum(r[1] for r in rows)
print("=" * 72)
print(f"检索命中：{hit}/{len(rows)}    总耗时 {cost:.1f}s    平均 {cost / len(rows):.2f}s/题")
print("=" * 72)
for q, ok, rank, n in rows:
    mark = "✅" if ok else "❌"
    where = f"第{rank}段/共{n}段" if rank else f"未命中/共{n}段"
    print(f"{mark}  {q[:34]:36s} {where}")
bad = [q for q, ok, _, _ in rows if not ok]
print()
print("检索失败：", bad if bad else "无")
