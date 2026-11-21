import sys, os
sys.path.insert(0, os.getcwd())
from loguru import logger; logger.remove()
import bid_eval as ev, selfcheck as sc

CASES = [
    ("投标保证金可以分期缴纳吗？",
     "可以。投标保证金允许分两期缴纳：第一期 50% 需在投标截止时间前 3 个工作日缴纳，第二期在中标通知书发出后 5 个工作日内补齐。"),
    ("投标文件可以用电子邮件提交吗？",
     "可以。投标文件允许通过电子邮件提交，收件邮箱为 zb@csggzy.cn，邮件主题需注明项目编号与投标人名称。"),
    ("项目经理需要几年以上工作经验？",
     "项目经理需具备 5 年以上同类工程施工管理经验，且须提供近 3 年的社保证明。"),
]

for q, fake in CASES:
    docs = ev.retrieve(q, False)
    bad = sc.verify_claims(fake, docs)
    print("=" * 66)
    print("问：", q)
    print("编造答案：", fake[:60], "...")
    print(f"裁判：抓到 {len(bad)} 条无依据")
    for b in bad:
        print("   -", b[:70])
