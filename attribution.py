"""条款级归因校验：每条断言都要能在原文找到出处，且**主体一致**。

为什么要这一层（D1 的 #19）：
    问"履约担保什么情况下不予退还"，模型答的 4 条其实出自 3.4.7
    「**投标担保**不予退还」——出处找得到，但主体是别的条款。
    这种错误：关键词判分看不出来、措辞检测也看不出来（它说得很肯定）。

判定三档：
    OK        出处找得到（且主体对得上，或断言本身没有主体）
    NO_SOURCE 原文里找不到这条断言的依据
    MISMATCH  出处找得到，但出处讲的是另一个主体（错位引用）

实现要点：PDF 抽取的文本里数字和单位之间常有空格（"90 天"、"150627581.27 元"），
所以比对前要把空白全部去掉；去掉后下标会变，故建一张「归一化下标 → 原文下标」的映射表，
这样还能回到原文取上下文给人看。
"""
import re

# 文档里的"主体"（条款对象）。判定错位靠它。
SUBJECTS = (
    "履约担保", "履约保证金", "投标担保", "投标保证金", "质量保证金",
    "投标有效期", "最高投标限价", "暂列金额", "设计费", "评标委员会",
    "中标候选人", "否决投标", "基准日期", "投标文件",
)

NUM_RE = re.compile(r"\d+(?:\.\d+)?(?:%|万元|元|天|个工作日|份|年)?")
BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.、)]|[（(]\d+[)）])\s*")
CJK_RE = re.compile(r"[\u4e00-\u9fa5]{6,}")


def normalize(text: str):
    """去掉所有空白，并返回「归一化下标 → 原文下标」映射表。"""
    out, idx = [], []
    for i, ch in enumerate(text):
        if ch.isspace() or ch in "\u201c\u201d\u2018\u2019\"\u300c\u300d\u3010\u3011":
            continue
        out.append(ch)
        idx.append(i)
    return "".join(out), idx


def split_claims(answer: str):
    lines = [BULLET_RE.sub("", ln).strip() for ln in answer.splitlines()]
    claims = [ln for ln in lines if len(ln) >= 6]
    return claims or [answer.strip()]


def subject_of(text: str):
    hits = [(text.find(s), s) for s in SUBJECTS if s in text]
    return min(hits)[1] if hits else None


def anchors_of(claim_norm: str, full_norm: str):
    """抽"可以拿去原文搜"的锚。

    1) 带单位的数字优先（90天 / 3% / 150627581.27元）——数字几乎不会被改写；
    2) 没有数字时，从断言里切所有 4~12 字的连续中文片段，
       挑**在原文里真实存在的最长那段**（模型会换语序，但很少换掉整段术语）。
    """
    nums = [m.group(0) for m in NUM_RE.finditer(claim_norm)]
    nums = [n for n in nums if len(n) >= 3 or n.endswith(("%", "元", "天", "份"))]
    if nums:
        return nums

    best = ""
    for run in CJK_RE.findall(claim_norm):
        for size in range(min(12, len(run)), 3, -1):
            for i in range(0, len(run) - size + 1):
                cand = run[i:i + size]
                if cand in full_norm and len(cand) > len(best):
                    best = cand
    return [best] if best else []


def verify_claim(claim: str, full_norm: str, orig: list, window: int = 200):
    claim_norm = re.sub(r"\s+", "", claim)
    subj = subject_of(claim_norm)
    anchors = anchors_of(claim_norm, full_norm)
    if not anchors:
        return "NO_SOURCE", "", ""

    best = None
    for a in anchors:
        pos = full_norm.find(a)
        if pos >= 0:
            best = (a, pos)
            break
    if not best:
        return "NO_SOURCE", "", anchors[0]

    a, pos = best
    seg = full_norm[max(0, pos - window): pos + window]
    if subj and subj not in seg:
        other = subject_of(seg)
        if other:
            start = orig[max(0, pos - window)]
            end = orig[min(len(orig) - 1, pos + window)]
            return "MISMATCH", f"[原文 @ {start}-{end}] " + seg[:260], a
    return "OK", "", a


def verify_answer(answer: str, full_norm: str, orig: list):
    rows = []
    for c in split_claims(answer):
        verdict, seg, anchor = verify_claim(c, full_norm, orig)
        rows.append({"claim": c, "verdict": verdict, "anchor": anchor, "seg": seg})
    return rows
