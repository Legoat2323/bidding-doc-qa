"""验证「触发 → 换问法重查 → 救回」这条链路本身通不通。

为什么不用模型自然产出的错答案来测：
    对抗测试里模型在上下文不足时一律拒答（13 次注入，0 次编造），
    所以自然路径上根本没有可触发的东西。这里**人工造一句无依据的话**，
    单独验证"如果它真说了没依据的话，机制抓不抓得到、救不救得回来"。
    这是链路测试，不是模型测试 —— 两者结论要分开写。
"""
import os, sys
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_ROOT); sys.path.insert(0, _ROOT)
_LIBS = os.path.join(os.path.dirname(_ROOT), "libs")
if os.path.isdir(_LIBS) and _LIBS not in sys.path: sys.path.insert(0, _LIBS)
from dotenv import load_dotenv; load_dotenv()
from loguru import logger; logger.remove(); logger.add(sys.stderr, level="ERROR")
import bid_eval as ev, selfcheck as sc

Q = "质量保证金的比例是多少？"
docs = ev.retrieve(Q, False)
fake = "- 质量保证金比例为 5%的工程款，在竣工结算时一次性扣留。(p.174)"
print("原始答案（人工构造，原文写的是 3%）：", fake)
print("上下文里有没有 5%：", "5%" in ev.ctx_of(docs))

bad = sc.verify_claims(fake, docs)
print("\n第 1 轮校验：无依据 %d 条" % len(bad))
for b in bad: print("   -", b[:70])

if bad:
    q2 = sc.refine_query(Q, bad)
    print("\n换问法：", q2[:80])
    docs2 = ev.retrieve(q2, False)
    ans2 = ev.generate(q2, docs2, False)
    bad2 = sc.verify_claims(ans2, docs2)
    print("第 2 轮答案：", ans2.replace(chr(10), " ")[:120])
    print("第 2 轮校验：无依据 %d 条" % len(bad2))
    print("\n救回：", "✅ 3% 回来了" if "3%" in ans2 else "❌ 仍是 %s" % ans2[:40])
else:
    print("\n校验没抓到 —— 机制失效")