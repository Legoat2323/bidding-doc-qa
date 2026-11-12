"""事实校验：把答案里的数字逐个回原文核对。

为什么需要：招投标场景里答错一个金额 = 废标 = 赔钱。
所以"看起来对"不够，要能证明这个数字确实来自原文。

局限（要诚实）：这是「数值存在性」校验，只能挡住编造的数字，
不能证明语义正确（比如把保证金金额说成限价，数字都在原文里，但用错了）。
"""
import re

# 带单位的数字才算「事实性声明」，纯数字多半是页码/序号
# 数字部分提取为第一组，单位为第二组
CLAIM_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(万元|元|%|日历天|天|年)")

#answer是大模型生成的答案   context是检索到的原文资料
def verify_claims(answer: str, context: str) -> tuple[int, list[str]]:
    """返回 (校验的数量, 未在原文找到的列表)。"""
    if not context:
        return 0, []
    #给检索到的原文“卸妆” 变成纯文本
    norm_ctx = context.replace(",", "").replace("，", "").replace(" ", "")
    claims: dict[tuple[str, str], bool] = {}

    # 提取答案里的数字部分（忽略千分位的逗号）和单位
    for m in CLAIM_RE.finditer(answer or ""):
        val = m.group(1).replace(",", "")
        unit = m.group(2)
        # 忽略个位数（多半是页码/序号）
        unit = m.group(2)
        # 个位数多半是页码/序号，忽略；但百分比例外，3% 也是有意义的数字
        if len(val.replace(".", "")) < 2 and unit != "%":
            continue
        # 记录这个数字和单位
        claims[(val, unit)] = True

    def found(v: str, u: str) -> bool:
        # 百分比的数字很短（3、5），单独找会被金额里的数字误命中，
        # 所以必须连着 % 一起匹配
        token = f"{v}%" if u == "%" else v
        return token in norm_ctx

    missing = [f"{v} {u}" for (v, u) in claims if not found(v, u)]
    return len(claims), missing


def verdict_md(total: int, missing: list[str]) -> str:
    """生成界面上的校验结果。"""
    if total == 0:
        return ""
    if not missing:
        return f"\n\n---\n\n✅ **事实校验**：答案里的 {total} 个数值，都能在原文片段中找到。"

    items = "、".join(f"`{m}`" for m in missing)
    return (
        f"\n\n---\n\n⚠️ **事实校验**：{total} 个数值中有 {len(missing)} 个"
        f"**未在原文找到**：{items}\n\n"
        f"这几个数字可能是模型补的，用之前请回原文核对。"
    )
