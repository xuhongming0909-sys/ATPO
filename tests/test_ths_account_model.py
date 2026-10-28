# AI-SUMMARY: 同花顺资金账户标签与唯一匹配模型测试

from execution.ths_account_ui import FundAccountRef, match_fund_account

def test_fund_account_ref_never_exposes_full_account():
    ref = FundAccountRef.from_label(0, "平安证券-1234567890")
    safe = ref.safe_dict()
    assert ref.fund_account_hash
    assert safe["fund_account_tail4"] == "7890"
    assert "1234567890" not in repr(safe)
    assert "1234567890" not in str(safe)

def test_match_by_masked_text_or_tail4_without_name():
    options = [
        FundAccountRef.from_label(0, "平安证券-1234567890"),
        FundAccountRef.from_label(1, "华宝证券-1234561111"),
    ]
    assert match_fund_account(options, {"fund_account_tail4": "1111"})[0].index == 1
    assert match_fund_account(options, {"display_masked": "平安证券-123****7890"})[0].index == 0
    assert match_fund_account(
        options,
        {"display_masked": "平安证券-123****7890", "fund_account_tail4": "7890"},
    )[0].index == 0
    assert match_fund_account(options, {"fund_account_tail4": "9999"})[1] == "FUND_ACCOUNT_NOT_FOUND"

def test_match_masked_text_tolerates_unique_ocr_noise():
    options = [
        FundAccountRef.from_label(0, "平安证券-2234567890"),
        FundAccountRef.from_label(1, "华宝证券-2234561111"),
    ]
    matched, code = match_fund_account(options, {"display_masked": "平安证券-223****789O"})
    assert code == ""
    assert matched.index == 0

def test_account_label_removes_menu_status_decorations():
    option = FundAccountRef.from_label(0, "平安证券-张*龙")
    target = FundAccountRef.from_label(0, "平安证券-张*龙 委托交易 F12已登录")
    matched, code = match_fund_account([option], target)
    assert code == ""
    assert matched.index == 0



def test_strict_match_does_not_fuzzy_select_another_account():
    options = [FundAccountRef.from_label(0, "中信建投证券-许*鸣融")]
    matched, code = match_fund_account(
        options,
        {"display_text": "中信建投证券-许*鸣"},
        allow_fuzzy=False,
    )
    assert matched is None
    assert code == "FUND_ACCOUNT_NOT_FOUND"


def test_display_identity_normalizes_ocr_separator_noise():
    options = [FundAccountRef.from_label(0, "平安证券-许*峰")]
    matched, code = match_fund_account(
        options,
        {"display_text": "国 平安证券一许*峰"},
        allow_fuzzy=False,
    )
    assert code == ""
    assert matched.index == 0
