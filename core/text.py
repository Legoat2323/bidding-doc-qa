"""文档片段的处理：去重、出处标注、拼上下文。

这里是纯逻辑，不依赖模型、不依赖 UI，可以单独测。
"""
from typing import Iterable


def dedup_docs(docs: Iterable, threshold: float = 0.8) -> list:
    """去掉内容重叠的片段。

    切分时 chunk_overlap=200，相邻块会有重复内容。不去重的话，
    模型会把同一句话列好几遍（实测出现过 28 条里 20 条重复）。

    两种重复都要处理：
        1. 完全相同的块 —— 前缀相同就能判
        2. 真重叠（chunk2 的开头是 chunk1 的结尾）—— 前缀不同，要比相似度

    片段最多 5 条，两两比较的开销可以忽略。
    """
    out = []
    for d in docs:
        if any(_too_similar(d.page_content, kept.page_content, threshold) for kept in out):
            continue
        out.append(d)
    return out


def _too_similar(a: str, b: str, threshold: float = 0.9) -> bool:
    """三种重复的判断，从便宜到贵依次尝试。"""
    if not a or not b:
        return False

    # 1) 前 80 字一样 —— 基本就是同一块（不同文件里重复出现的内容）
    head = 80
    if a[:head].replace("\n", "").replace(" ", "") == b[:head].replace("\n", "").replace(" ", ""):
        return True

    # 2) 真重叠：chunk2 的开头就是 chunk1 的结尾（chunk_overlap 造成的）
    if _is_overlap(a, b) or _is_overlap(b, a):
        return True

    # 3) 高相似度兜底。只在长度接近时比较，避免短块被长块吞掉
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) / len(longer) < 0.5:
        return False

    from difflib import SequenceMatcher

    return SequenceMatcher(None, a, b).ratio() >= threshold


def _is_overlap(a: str, b: str, min_len: int = 100) -> bool:
    """b 的开头是否是 a 的结尾（长度至少 min_len）。"""
    limit = min(len(a), len(b))
    if limit < min_len:
        return False
    # 逐字判断。步子跨大了会漏掉真实重叠长度（实测 stride=10 就漏了 120 字的情况），
    # 片段本身只有几百字，开销可以忽略。
    for n in range(limit, min_len - 1, -1):
        if a.endswith(b[:n]):
            return True
    return False


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
