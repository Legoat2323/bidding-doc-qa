"""文本处理（去重、出处标注、上下文拼装）的单元测试。"""
from core.text import build_context, dedup_docs, format_sources, page_label


class FakeDoc:
    """模拟 langchain 的 Document，避免测试依赖真实模型。"""

    def __init__(self, text, page=None):
        self.page_content = text
        self.metadata = {} if page is None else {"page": page}


def test_dedup_identical_chunks():
    """同一块内容出现两次（不同文件里常有），只留一份。"""
    body = "请假流程：普通员工由直属领导审批，抄送考勤组、请假部门、人事行政经理。" * 3
    docs = [FakeDoc(body), FakeDoc(body), FakeDoc("销假流程：假期结束后第一个工作日内办理。")]
    out = dedup_docs(docs)
    assert len(out) == 2


def test_dedup_chunk_overlap():
    """真重叠：下一块的开头就是上一块的结尾（chunk_overlap 造成的）。"""
    first = "第一节内容讲的是投标人须知和评标办法。" * 10
    second = first[-120:] + "第二节新增内容。"
    out = dedup_docs([FakeDoc(first), FakeDoc(second)])
    assert len(out) == 1, "重叠块应该被去掉，否则模型会重复回答"


def test_dedup_keeps_different_chunks():
    docs = [FakeDoc("第一条完全不同的内容" * 5), FakeDoc("第二条也是不同的内容" * 5)]
    assert len(dedup_docs(docs)) == 2


def test_page_label_pdf():
    assert page_label(FakeDoc("x", page=55), 1) == "p.55"


def test_page_label_docx_fallback():
    """docx 没有页码元数据，退化成片段序号。"""
    assert page_label(FakeDoc("x"), 3) == "第3段"


def test_build_context_has_refs():
    docs = [FakeDoc("内容甲", page=55), FakeDoc("内容乙")]
    ctx = build_context(docs)
    assert "[p.55]" in ctx
    assert "[第2段]" in ctx
    assert "内容甲" in ctx and "内容乙" in ctx


def test_format_sources():
    docs = [FakeDoc("很长的内容" * 100, page=10)]
    md = format_sources(docs)
    assert "p.10" in md
    # 截断到 300 字，不能整段塞进去
    assert len(md) < 400
