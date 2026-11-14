# -*- coding: utf-8 -*-
"""
Holdout 验收集（8 题，6 道有答案 + 2 道无答案）

规则（很重要）：
1. 这 8 道题**永远不参与调参**。改 k、改阈值、改分词，都不看这 8 道的结果。
2. **不自动判分**。每一题的答案由人眼看，判断"有没有把该说的话说对"。
   —— 因为字符串匹配会撒谎（见 2026-11-13 的教训：PDF 把 2023-12-20 抽成 2023 -12-20）。
3. 跑一次 ≈ 3 分钟，输出写进 holdout_report.md，判分栏留空给人填。

用法：
    ./run_exp.cmd holdout.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
os.chdir(_ROOT)
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT.parent / "libs"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from loguru import logger  # noqa: E402

logger.remove()
logger.add(sys.stderr, level="WARNING")

from combine_client import CombineClient  # noqa: E402

DOC = "招标文件正文22.pdf"

# (问题, 标准答案（原文摘录，供人眼比对）, 出处页)
CASES = [
    (
        "投标担保的金额是多少？",
        "人民币伍拾万元（￥500000 元）",
        17,
    ),
    (
        "类似工程业绩的考核期限是多久？",
        "1095 天，按工程竣工验收文件中建设单位签字之日起计算",
        23,
    ),
    (
        "中标候选人是怎么推荐和确定的？",
        "评定分离法：推荐不超过 3 个不排序的中标候选人，招标人以票决法（直接票决）确定中标人",
        20,
    ),
    (
        "是否允许递交备选投标方案？",
        "不允许",
        19,
    ),
    (
        "国家级施工奖项和省级施工奖项分别包括哪些？",
        "国家级施工奖项：鲁班奖、国家优质工程奖；省级施工奖项：芙蓉奖、省优质工程奖",
        23,
    ),
    (
        "履约担保的金额是多少？",
        "中标金额的 10%",
        20,
    ),
    # ---- 下面两题文档里没有答案，正确回答必须是"文件中未提及" ----
    (
        "投标保证金在退还时是否计算利息？",
        "【无答案】文档只规定了逾期付款/质保金的利息，没有投标保证金利息的条款",
        None,
    ),
    (
        "投标人是否需要提供近三年经审计的财务报表？",
        "【有答案，差点被我误判成无答案】p.25：净资产及资产负债率以投标人【上一年度】经会计事务所审计的"
        "财务报表复印件为准；1/1–4/30 无法提供的可用再上一年度。注意是“上一年度”，不是“近三年”。",
        25,
    ),
]


def main() -> None:
    client = CombineClient()
    client.load_knowledge()

    rows = []
    for i, (q, gold, page) in enumerate(CASES, 1):
        print(f"[{i}/{len(CASES)}] {q}", flush=True)
        client.clear_history()
        result = client.invoke(q, DOC, max_length=1500, temperature=0.1)
        docs = result.get("context", [])
        answer = (result.get("answer") or "").strip()

        pages = sorted({d.metadata.get("page", "?") for d in docs})
        rows.append({"q": q, "gold": gold, "page": page, "pages": pages, "answer": answer})
        print(f"    片段页码 {pages}", flush=True)
        print(f"    回答 {answer[:60].replace(chr(10), ' ')}", flush=True)

    out = Path(__file__).with_name("holdout_report.md")
    lines = [
        "# Holdout 验收报告（8 题）",
        "",
        "> 判分规则：**人眼看**。回答把该说的说对了 = ✅；说错 = ❌；",
        "> 无答案的题硬编 = ❌，说“文件中未提及” = ✅。",
        "",
        "| # | 问题 | 标准答案 | 检索页码 | 判分 | 备注 |",
        "|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(rows, 1):
        gold = r["gold"].replace("|", "\\|")
        pg = "、".join(str(p) for p in r["pages"])
        lines.append(f"| {i} | {r['q']} | {gold} | {pg} |  |  |")

    lines += ["", "## 逐题回答原文", ""]
    for i, r in enumerate(rows, 1):
        lines += [f"### {i}. {r['q']}", "", "**回答：**", "", "```", r["answer"], "```", ""]

    out.write_text("\n".join(lines), encoding="utf-8")
    print()
    print(f"报告已写入：{out}")
    print("下一步：打开这个文件，逐题判 ✅/❌，填进“判分”栏。")


if __name__ == "__main__":
    main()
