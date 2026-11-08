"""从招标文件片段里结构化抽取「评标权重」。

为什么单独抽：权重数值藏在 PDF 表格里，文字层抽出来是碎片，
embedding 检索不到，让模型"读一下再说"它会编。所以绕开模型，用正则。

这是当前最脆弱的一环——换一种排版格式可能失效，已知且在 README 里写明了。
"""
import re

WEIGHT_RE = re.compile(
    r"(技术方案权重|企业资信及履约能力|投标报价权重)"
    r"\s*[Jj]?\s*([123])?\s*[（(]([^)）]*)[)）]\s*[:：]\s*([0-9.]+)"
)


def extract_weights(docs) -> str:
    """返回 markdown 表格；抽不到返回空字符串。"""
    found = {}
    for d in docs:
        text = d.page_content.replace("\n", " ")
        for m in WEIGHT_RE.finditer(text):
            name = m.group(1)
            if name in found:
                continue
            found[name] = {
                "code": m.group(2) or "",
                "range": m.group(3).replace("取值范围", "").strip(" ：:"),
                "value": m.group(4),
                "page": d.metadata.get("page", "?"),
            }
    if not found:
        return ""

    rows = [
        "| 评审因素 | 权重代号 | 取值范围 | 权重值 | 出处 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, info in found.items():
        rows.append(
            f"| {name} | J{info['code']} | {info['range']} | **{info['value']}** | p.{info['page']} |"
        )
    return "\n".join(rows)
