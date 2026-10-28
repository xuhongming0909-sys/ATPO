# AI-SUMMARY: 验证资金账户菜单点击后不发送 ESC，且直登行完整等待登录弹窗。

from execution.ths_account_model import FundAccountRef
from execution.ths_account_ui import ThsAccountUI
from shared.errors import AutoIpoError


def _cfg(dialog_wait_s=5.0):
    return {
        "gui": {
            "ths_account_switch": {
                "dialog_wait_s": dialog_wait_s,
                "login_wait_s": 15,
                "fund_login_result_wait_s": 15,
                "fund_login_poll_interval_s": 0.5,
            },
            "xiadan": {
                "account_combo_control_id": 2322,
                "fund_account_control_id": 1711,
            },
        }
    }


def test_click_main_row_does_not_send_escape_after_click():
    close_calls = []

    ui = ThsAccountUI(
        client=object(),
        cfg=_cfg(),
        open_menu_fn=lambda: "menu",
        read_rows_fn=lambda _menu: [
            {"index": 0, "text": "甲-1234567890", "top": 10, "bottom": 36},
        ],
        click_row_fn=lambda _menu, _row, _total: None,
        close_menu_fn=lambda: close_calls.append("ESC"),
    )

    ui._click_main_row(FundAccountRef.from_label(0, "甲-1234567890"))

    assert close_calls == []


def test_menu_click_preserves_exact_row_bounds():
    clicked = []
    ui = ThsAccountUI(
        client=object(),
        cfg=_cfg(),
        open_menu_fn=lambda: "menu",
        read_rows_fn=lambda _menu: [
            {"index": 0, "text": "编辑账户", "top": 0, "bottom": 8},
            {"index": 1, "text": "甲-1234567890", "top": 10, "bottom": 36},
        ],
        click_row_fn=lambda _menu, row, _total: clicked.append(dict(row)),
        close_menu_fn=lambda: None,
    )

    ui._click_main_row(FundAccountRef.from_label(0, "甲-1234567890"))

    assert clicked == [{
        "index": 1,
        "text": "甲-1234567890",
        "top": 10,
        "bottom": 36,
    }]


def test_menu_click_uses_uia_text_control_center(monkeypatch):
    import pywinauto.mouse as mouse

    clicked = []
    monkeypatch.setattr(mouse, "click", lambda coords: clicked.append(coords))
    ui = ThsAccountUI(
        client=object(),
        cfg=_cfg(),
        open_menu_fn=lambda: "menu",
        read_rows_fn=lambda _menu: [{
            "index": 0,
            "text": "国 平安证券-甲*",
            "top": 10,
            "bottom": 36,
            "left": 100,
            "right": 260,
            "click_x": 180,
            "click_y": 23,
        }],
        click_row_fn=lambda _menu, _row, _total: None,
        close_menu_fn=lambda: None,
    )

    row = ui._account_rows(ui._read_rows_fn("menu"))[0]
    from execution.hexin_login import _default_click_row
    _default_click_row("menu", row, 1, ui._hexin_settings())

    assert clicked == [(180, 23)]


def test_xiadan_main_window_is_not_mistaken_for_fund_login_dialog():
    ui = ThsAccountUI(client=object(), cfg=_cfg())

    is_login = ui._is_fund_login_row({
        "title": "委托下单",
        "texts": ["资金余额", "登录", "退出"],
    })

    assert is_login is False


def test_direct_row_waits_full_dialog_window():
    ui = ThsAccountUI(client=object(), cfg=_cfg(dialog_wait_s=5.0))
    waits = []
    ui._click_main_row = lambda _ref: {"text": "甲-1234567890"}
    ui._dialogs_after_click = lambda timeout_s: waits.append(timeout_s) or []
    ui._ensure_xiadan_fn = lambda client: None
    ui._xiadan_identity = lambda: (True, "1234567890", "甲", ["甲"])

    result = ui.login_fund_account(FundAccountRef.from_label(0, "甲-1234567890"))

    assert result.status == "ready"
    assert waits == [5.0]


def test_fund_login_result_polls_until_target_enters_xiadan():
    ui = ThsAccountUI(
        client=object(),
        cfg=_cfg(dialog_wait_s=0.2),
        sleep_fn=lambda _seconds: None,
    )
    attempts = []
    switched = []

    def switch_target(_ref):
        attempts.append(1)
        if len(attempts) < 4:
            raise AutoIpoError(
                "FUND_ACCOUNT_NOT_FOUND",
                "目标暂未进入 xiadan",
                "继续等待登录结果",
            )
        switched.append(1)

    ui._click_main_row = lambda _ref: {"text": "甲-1234567890"}
    ui._dialogs_after_click = lambda _timeout_s: []
    ui._ensure_xiadan_fn = lambda client: None
    ui._xiadan_identity = lambda: (
        True,
        "1234567890" if switched else "9999999990",
        "甲" if switched else "乙",
        ["甲"],
    )
    ui._switch_xiadan_target = switch_target

    result = ui.login_fund_account(FundAccountRef.from_label(0, "甲-1234567890"))

    assert result.status == "ready"
    assert len(attempts) == 4
