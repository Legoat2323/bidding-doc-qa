"""表格数值抽取的单元测试。"""
from core.extract import extract_weights


class FakeDoc:
    def __init__(self, text, page=None):
        self.page_content = text
        self.metadata = {} if page is None else {"page": page}


# 来自招标文件 p.55 的真实排版（PDF 抽出来是一串，没有换行）
REAL_PAGE = (
    "(总权值1) 技术方案权重 J1（取值范围：0.05-0.30）：0.25 "
    "企业资信及履约能力 J2（取值范围：0.35-0.45）：0.40 "
    "投标报价权重 J3（取值范围：0.35-0.5）：0.35"
)


def test_extract_three_weights():
    md = extract_weights([FakeDoc(REAL_PAGE, page=55)])
    assert "0.25" in md and "0.40" in md and "0.35" in md
    assert "J1" in md and "J3" in md
    assert "p.55" in md


def test_extract_returns_empty_when_no_match():
    md = extract_weights([FakeDoc("这段文字里没有任何权重信息。")])
    assert md == ""


def test_extract_with_full_width_parens():
    """正则要同时兼容中文括号和英文括号。"""
    text = "技术方案权重 J1(取值范围：0.10-0.20)：0.15"
    md = extract_weights([FakeDoc(text, page=1)])
    assert "0.15" in md


def test_extract_keeps_first_occurrence():
    """同一权重出现多次时取第一次，避免表格重复行。"""
    text1 = "技术方案权重 J1（取值范围：0.05-0.30）：0.25"
    text2 = "技术方案权重 J1（取值范围：0.05-0.30）：0.99"
    md = extract_weights([FakeDoc(text1, page=55), FakeDoc(text2, page=99)])
    assert "0.25" in md
    assert "0.99" not in md
