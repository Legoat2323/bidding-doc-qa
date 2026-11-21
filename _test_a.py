import sys, os
sys.path.insert(0, os.getcwd())
from loguru import logger; logger.remove()
import bid_eval as ev
import selfcheck as sc

QS = [
    "投标保证金可以分期缴纳吗？",
    "投标文件可以用电子邮件提交吗？",
    "项目经理需要几年以上工作经验？",
]

for q in QS:
    docs = ev.retrieve(q, False)
    ans = ev.generate(q, docs, False)
    bad = sc.verify_claims(ans, docs)
    print("=" * 70)
    print("问：", q)
    print("答：", ans.replace("\n", " ")[:180])
    print(f"裁判：无依据 {len(bad)} 条", ("→ 抓到" if bad else "→ 没抓到"))
    for b in bad:
        print("   -", b[:60])
