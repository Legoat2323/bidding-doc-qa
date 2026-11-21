import sys, os, time
sys.path.insert(0, os.getcwd())
from loguru import logger; logger.remove()
import bid_eval as ev, selfcheck as sc

def run():
    a_hit = a_ok = b_ok = 0
    t0 = time.time()
    for q, kws, is_t in ev.CASES:          # 第三个字段是 is_template，不是 no_answer
        docs = ev.retrieve(q, is_t)
        if docs: a_hit += 0
        if ev.hit_any(ev.ctx_of(docs), kws): a_hit += 1
        ans, status, rounds = sc.answer_with_selfcheck(q, is_template=is_t)
        ok = ev.hit_any(ans, kws); a_ok += ok
        print(f"[A] {'✅' if ok else '❌'} {q[:24]}  {ans[:56]}  ({status}/{rounds}轮)")
    for q in ev.REFUSAL_CASES:
        ans, status, rounds = sc.answer_with_selfcheck(q, is_template=False)
        ok = any(w in ans for w in ev.NO_ANSWER_WORDS); b_ok += ok
        print(f"[B] {'✅' if ok else '❌'} {q[:24]}  {ans[:56]}  ({status}/{rounds}轮)")
    n_a, n_b = len(ev.CASES), len(ev.REFUSAL_CASES)
    print(f"\nA 检索 {a_hit}/{n_a}  A 回答 {a_ok}/{n_a}  B 拒答 {b_ok}/{n_b}  综合 {a_ok+b_ok}/{n_a+n_b}")
    print(f"总耗时 {time.time()-t0:.1f}s")

run()
