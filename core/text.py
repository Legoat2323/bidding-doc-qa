"""文档片段的处理：去重、出处标注、拼上下文。

这里是纯逻辑，不依赖模型、不依赖 UI，可以单独测。
"""
from typing import Iterable


def dedup_docs(docs: Iterable) -> list:
    """去掉内容重叠的片段。

    切分时 chunk_overlap=200，相邻块会有重复内容。不去重的话，
    模型会把同一句话列好几遍（实测出现过 28 条里 20 条重复）。
    """
    seen, out = set(), []
    for d in docs:
        key = d.page_content[:80].replace("\n", "").replace(" ", "")
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
    return out


def page_label(doc, idx: int) -> str:
    """PDF 有页码，docx/txt 没有，退化成片段序号。"""
    page = doc.metadata.get("page")
    return f"p.{page}" if page is not None else f"第{idx}段"


def build_context(docs: Iterable) -> str:
    """拼成带出处标记的上下文，模型照着标记引用即可。"""
    return "\n\n".join(
        f"[{page_label(d, i)}] {d.page_content}" for i, d in enumerate(docs, 1)
    )


def format_sources(docs: Iterable, limit: int = 5) -> str:
    """界面下方「原文依据」的 markdown。"""
    lines = []
    for i, d in enumerate(list(docs)[:limit], 1):
        body = d.page_content.replace("\n", " ").strip()
        lines.append(f"**[{i}] {page_label(d, i)}**\n\n> {body[:300]}\n")
    return "\n".join(lines)
