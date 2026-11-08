"""事实校验的单元测试。

这些用例都来自实际踩过的坑，不是为了凑覆盖率。
运行：pytest tests/ -v
"""
from core.verify import verdict_md, verify_claims

CTX = (
    "本项目最高投标限价总价为150627581.27元，质量保证金不得高于3%。"
    "总工期360日历天。"
)


def test_all_numbers_found():
    """答案里的数字都在原文里 → 不报警。"""
    answer = "最高限价 150,627,581.27 元。质量保证金 3%。"
    total, missing = verify_claims(answer, CTX)
    assert total == 2
    assert missing == []


def test_fabricated_money_caught():
    """编造的金额必须被抓出来。"""
    answer = "最高限价 150000000 元。"
    total, missing = verify_claims(answer, CTX)
    assert total == 1
    assert "150000000 元" in missing


def test_fabricated_percent_caught():
    """百分比的坑：5 这个字符在金额里也出现过，不能误判为「找到」。"""
    answer = "质量保证金不得高于 5%。"
    total, missing = verify_claims(answer, CTX)
    assert total == 1
    assert any("5" in m for m in missing)


def test_page_number_ignored():
    """个位数（页码/序号）不参与校验，避免噪音。"""
    answer = "见第 5 页。"
    total, missing = verify_claims(answer, CTX)
    assert total == 0


def test_comma_normalized():
    """原文没逗号、答案有逗号，也要能匹配上。"""
    answer = "限价 150,627,581.27 元"
    _, missing = verify_claims(answer, CTX)
    assert missing == []


def test_empty_context():
    """没有上下文就不校验（而不是全部报错）。"""
    total, missing = verify_claims("1234567 元", "")
    assert total == 0
    assert missing == []


def test_verdict_text():
    assert verdict_md(0, []) == ""
    assert "✅" in verdict_md(2, [])
    assert "⚠️" in verdict_md(2, ["999 元"])
