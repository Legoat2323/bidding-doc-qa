"""方案 B：生成后自检循环（断言校验 → 换问法重检索 → 仍无依据则拒答）"""
import json
import re

import bid_eval as ev
import slots
from models import get_lc_model_client

_judge = get_lc_model_client(temperature=0.0, max_tokens=600)

VERIFY_PROMPT = """你是招投标文件的审校员。

【原文片段】
{context}

【待校验答案】
{answer}

任务：逐条检查答案里的每个结论，判断它能否在【原文片段】中找到明确依据。
注意：
- 只说"依据"而不是"合理"。数字、比例、期限、主体名称必须能在片段里找到。
- 如果答案说"未提及/未规定"，那本身是有依据的，不算无依据。

只输出 JSON，不要任何解释文字：
{{"unsupported": ["无依据的结论原文", ...]}}
全部有依据时输出 {{"unsupported": []}}
"""

REFUSE = "文件中未提及该内容。"


def _strip_json(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    return m.group(0) if m else "{}"


def verify_claims(answer, docs, ctx_fn=ev.ctx_of):
    """返回无依据的结论列表；解析失败时返回空列表（宁放过不误杀）。"""
    if not docs:
        return []
    raw = _judge.invoke(
        VERIFY_PROMPT.format(context=ctx_fn(docs), answer=answer)
    ).content
    try:
        data = json.loads(_strip_json(raw))
        return [s for s in data.get("unsupported", []) if s.strip()]
    except Exception:
        return []


def coverage_gap(q, docs, answer):
    """第 3 层：覆盖检查（纯代码，0 次调用）。返回缺失的原文片段列表。"""
    text = "\n".join(d.page_content for d in docs)
    r = slots.check_coverage(q, text, answer)
    return r["type"], r["missing"]


def regenerate_with_gaps(q, docs, answer, gaps, is_template=False):
    """漏答的修法是「重喂」不是「重查」：把缺的原文片段追加进上下文再生成一次。"""
    extra = "\n".join(g.split("] ", 1)[-1] for g in gaps)
    q2 = q + "\n\n请同时覆盖以下原文要点，不要遗漏：\n" + extra
    return ev.generate(q2, docs, is_template)


def refine_query(q, unsupported):
    """用"没依据的那几条"里最长的片段做新检索式，逼检索去找真正的条款。"""
    frag = sorted(unsupported, key=len, reverse=True)[0]
    frag = re.sub(r"[，。；：、（）()]", " ", frag)[:40]
    return f"{q} {frag} 条款 原文"


def answer_with_selfcheck(q, is_template=False, max_rounds=2, verbose=True):
    """返回 (answer, status, rounds)。status: ok / refused / refused-after-retry"""
    docs = ev.retrieve(q, is_template)
    ans = ev.generate(q, docs, is_template)
    if ("未提及" in ans) or ("未规定" in ans) or ("没有" in ans and len(ans) < 60):
        return ans, "refused", 1

    for rnd in range(1, max_rounds + 1):
        bad = verify_claims(ans, docs)
        if verbose:
            print(f"  第{rnd}轮校验：无依据 {len(bad)} 条")
            for b in bad:
                print(f"    - {b[:50]}")
        if not bad:
            qtype, gaps = coverage_gap(q, docs, ans)
            if verbose:
                print(f"  第{rnd}轮覆盖检查（{qtype}）：缺 {len(gaps)} 项")
                for g in gaps:
                    print(f"    - {g[:50]}")
            if gaps and rnd < max_rounds:
                ans2 = regenerate_with_gaps(q, docs, ans, gaps, is_template)
                _, gaps2 = coverage_gap(q, docs, ans2)
                if verbose:
                    print(f"  重喂后剩余缺失：{len(gaps2)} 项")
                if len(gaps2) < len(gaps):
                    return ans2, "coverage-fixed", rnd
            return ans, ("ok" if rnd == 1 else "retry-ok"), rnd
        if rnd == max_rounds:
            break
        q2 = refine_query(q, bad)
        if verbose:
            print(f"  换问法重检索：{q2[:60]}")
        docs = ev.retrieve(q2, is_template)
        ans = ev.generate(q2, docs, is_template)

    return REFUSE + "（原文只规定了相关流程，未给出被问及的情形）", "refused-after-retry", max_rounds
