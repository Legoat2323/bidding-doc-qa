"""CRAG 对抗测试：人为把检索打坏，看 selfcheck 会不会触发、能不能救回。

为什么需要这个：
    正常 23 题里自检 0 次触发 —— 机制跑通了，但没被验证过。这里把检索结果
    人为换成"坏上下文"，逼模型出错，再看自检抓不抓得到。

四种坏法（各自对应一种真实故障）：
    空上下文   —— 检索 0 命中（索引/阈值/切分出事）
    全错片段   —— 检索串了主题（问保证金，返回字体要求）
    混入错片段 —— 4 段对的 + 1 段"隔壁条款"（主体换了、格式一样）
                  #19 那次真事故就是这个形态：3.4.7 讲"投标担保"，被搬到"履约担保"上

每组都配一个"对照"：同一题、同一段代码、不注入坏上下文。
唯一变量是 docs，所以差异只能由 docs 解释。

用法：python experiments/exp_adversarial.py
"""
import json
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_ROOT)
sys.path.insert(0, _ROOT)
_LIBS = os.path.join(os.path.dirname(_ROOT), "libs")
if os.path.isdir(_LIBS) and _LIBS not in sys.path:
    sys.path.insert(0, _LIBS)

from dotenv import load_dotenv

load_dotenv()

from loguru import logger

logger.remove()
logger.add(sys.stderr, level="ERROR")

import bid_eval as ev
import selfcheck as sc

# 选这三题：答案都是能一眼核对的具体数字/条目，判"答错"不靠感觉
CASES = [
    dict(q="质量保证金的比例是多少？", keys=["3%"], tpl=False,
         unrelated="投标文件用什么字体？", sibling="投标保证金"),
    dict(q="投标有效期是多久？", keys=["90"], tpl=False,
         unrelated="评标委员会由几个人组成？", sibling="总工期多少天？"),
    dict(q="履约保证金什么情况下不予退还？",
         keys=["不履行合同", "转包", "挂靠"], tpl=False,
         unrelated="投标文件用什么字体？", sibling="投标保证金"),
]

ARMS = ["对照", "空上下文", "全错片段", "混入错片段"]

_orig_retrieve = ev.retrieve
_orig_verify = sc.verify_claims
_state = {"poison": []}
_calls = []


def _patched_retrieve(q, is_template):
    if _state["poison"]:
        return _state["poison"].pop(0)
    return _orig_retrieve(q, is_template)


def _patched_verify(answer, docs, *a, **kw):
    bad = _orig_verify(answer, docs, *a, **kw)
    _calls.append({"answer": answer, "n_docs": len(docs), "bad": bad})
    return bad


ev.retrieve = _patched_retrieve
sc.verify_claims = _patched_verify


def _pages(docs):
    return [str(d.metadata.get("page", "?")) for d in docs]


def run_one(case, arm):
    q, tpl = case["q"], case["tpl"]
    _state["poison"] = []
    _calls.clear()

    real = _orig_retrieve(q, tpl)
    poison = None
    if arm == "空上下文":
        poison = []
    elif arm == "全错片段":
        poison = _orig_retrieve(case["unrelated"], False)
    elif arm == "混入错片段":
        sib = _orig_retrieve(case["sibling"], case["sibling"] in ev.RETRIEVAL_QUERY)
        # 4 段对的 + 1 段"隔壁条款"，插在中间（模型最容易顺手引用）
        poison = real[:2] + sib[:1] + real[2:4]
    if poison is not None:
        _state["poison"] = [poison]

    t0 = time.time()
    ans, status, rounds = sc.answer_with_selfcheck(q, is_template=tpl, verbose=False)
    cost = time.time() - t0

    first = _calls[0] if _calls else None
    hit = ev.hit_any(ans, case["keys"])
    refused = any(w in ans for w in ev.NO_ANSWER_WORDS)
    return {
        "q": q,
        "arm": arm,
        "docs_pages": _pages(_state["poison"][0] if _state["poison"] else []),
        "injected": _pages(poison) if poison is not None else None,
        "real_pages": _pages(real),
        "verify_ran": bool(_calls),
        "first_answer": first["answer"] if first else ans,
        "unsupported": first["bad"] if first else [],
        "rounds": rounds,
        "status": status,
        "gold_hit": hit,
        "outcome": "答对" if hit else ("拒答" if refused else "答错"),
        "answer": ans,
        "secs": round(cost, 1),
    }


rows = []
for case in CASES:
    for arm in ARMS:
        r = run_one(case, arm)
        rows.append(r)
        print(f"[{r['arm']:<5}] {r['outcome']} rounds={r['rounds']} "
              f"无依据{len(r['unsupported'])}条 {r['secs']}s  {r['q']}")
        print(f"         答：{r['answer'].replace(chr(10), ' ')[:100]}")

# ---------------- 单独一节：复刻 #19 的"主体错位" ----------------
# #19 真事故的形态不是"上下文为空"，而是：检索回来的段落里，
#   有讲"履约担保提交/退还"的（主体对，但不回答"什么情况不退"），
#   也有讲"投标担保不予退还"的（回答得铿锵有力，但主体错了）。
# 模型于是把投标担保的规则搬到履约担保上 —— 而校验器只在
# "这句话能不能在片段里找到"这个层面看，所以它抓不到。
SHIFT_Q = "履约保证金什么情况下不予退还？"
SHIFT_KEYS = ["不履行合同", "转包", "挂靠"]
SHIFT_LEAK = ["撤销", "修改投标文件", "不签订合同", "拒签"]


def run_shift():
    _state["poison"] = []
    _calls.clear()
    sib = _orig_retrieve("投标担保不予退还的情形 撤销投标文件 中标后不签合同", False)
    rel = _orig_retrieve("履约担保 提交 退还 竣工验收合格后7天", False)
    picked = [d for d in sib if "投标担保" in d.page_content][:2] or sib[:2]
    poison = [d for d in picked + rel[:3] if "不履行合同" not in d.page_content]
    _state["poison"] = [poison]
    print("  [注入 %d 段]" % len(poison))
    for d in poison:
        print("    p.%s %s" % (d.metadata.get("page", "?"), d.page_content[:70].replace(chr(10), " ")))

    ans, status, rounds = sc.answer_with_selfcheck(SHIFT_Q, is_template=False, verbose=False)
    first = _calls[0] if _calls else None
    hit = ev.hit_any(ans, SHIFT_KEYS)
    return {
        "q": SHIFT_Q, "arm": "错位主体(#19复刻)", "docs_pages": _pages(poison),
        "injected": _pages(poison), "real_pages": [], "verify_ran": bool(_calls),
        "first_answer": first["answer"] if first else ans,
        "unsupported": first["bad"] if first else [],
        "rounds": rounds, "status": status, "gold_hit": hit,
        "outcome": "答对" if hit else "答错",
        "leak": ev.hit_any(ans, SHIFT_LEAK),
        "answer": ans, "secs": 0,
    }


print()
print("复刻 #19：把「投标担保」的条款混进「履约担保」的上下文，且故意不注入 15.2.1")
rows.append(run_shift())

saved = os.path.join("experiments", "adversarial_dump.json")
with open(saved, "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=2)

print()
print("=" * 82)
print(f"{'题':<34}{'组':<12}{'结果':<6}{'轮':<4}{'无依据'}")
print("-" * 82)
for r in rows:
    print(f"{r['q'][:16]:<20}{r['q'][16:24]:<14}{r['arm']:<12}{r['outcome']:<6}"
          f"{r['rounds']:<4}{len(r['unsupported'])}")

adv = [r for r in rows if r["arm"] != "对照"]
print()
ctrl = [r for r in rows if r["arm"] == "对照"]
print(f"对照 {len(ctrl)} 题：答对 {sum(r['outcome']=='答对' for r in ctrl)}/{len(ctrl)}，"
      f"触发 {sum(r['rounds']>1 for r in ctrl)}/{len(ctrl)}")
print(f"对抗 {len(adv)} 次：拒答 {sum(r['outcome']=='拒答' for r in adv)}，"
      f"答错 {sum(r['outcome']=='答错' for r in adv)}，"
      f"答对 {sum(r['outcome']=='答对' for r in adv)}")
print(f"          自检触发 {sum(r['rounds']>1 for r in adv)}，"
      f"触发后救回 {sum(r['rounds']>1 and r['gold_hit'] for r in adv)}")
print(f"明细已存 {saved}")
