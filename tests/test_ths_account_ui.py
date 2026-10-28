# AI-SUMMARY: 同花顺资金账户 UI 适配测试——全 mock 验证唯一控件、脱敏匹配、登录判据和弹窗优先关闭
import json
import types

import pytest

from execution.ths_account_ui import (
    FundAccountRef,
    HexinSwitchUI,
    ThsAccountUI,
    match_fund_account,
)
from shared.errors import AutoIpoError


class FakeControl:
    def __init__(self, control_id, text="", items=()):
        self._control_id = control_id
        self._text = text
        self._items = list(items)

    def control_id(self):
        return self._control_id

    def window_text(self):
        return self._text

    def item_texts(self):
        return list(self._items)


class FakeMain:
    def __init__(self, controls):
        self._controls = controls

    def descendants(self, class_name=""):
        return [c for c in self._controls if class_name == "ComboBox"]


def _cfg():
    return {
        "execution": {"ths_account_switch": {"max_fund_accounts_per_ths": 10}},
        "gui": {
            "ths_account_switch": {
                "login_wait_s": 1,
                "fund_login_result_wait_s": 1,
                "fund_login_poll_interval_s": 0.2,
            },
            "xiadan": {
                "fund_account_control_id": 1711,
                "account_combo_control_id": 2322,
            },
            "hexin_login": {
                "login_dialog_title": "委托下单",
                "login_dialog_keywords": ["资金账号", "交易密码", "验证码"],
            },
        },
    }


def _ui(current="1234567890", labels=("平安证券-1234567890",), dialogs=None, switch_value="1234567890"):
    state = {
        "current": current,
        "labels": list(labels),
        "rows": [{"index": i, "text": text, "top": i * 20} for i, text in enumerate(labels)],
        "dialogs": list(dialogs or []),
        "closed": [],
        "switch_value": switch_value,
        "switch_calls": [],
    }

    def main(_client):
        return FakeMain([
            FakeControl(1711, state["current"]),
            FakeControl(2322, state["labels"][0] if state["labels"] else "", state["labels"]),
        ])

    def close(records, _settings, _client):
        handler = state.get("close")
        if handler is not None:
            return handler(records, _settings, _client)
        state["closed"].extend(records)
        state["dialogs"] = []

    def click_row(_menu, row, _total):
        state["current"] = state["switch_value"]

    def switch_account(_raw, _timeout, _client):
        state["switch_calls"].append("switch_account")
        state["current"] = state["switch_value"]

    return ThsAccountUI(
        client=object(),
        cfg=_cfg(),
        current_value_fn=lambda _client: state["current"],
        main_window_fn=main,
        open_menu_fn=lambda: "menu",
        read_rows_fn=lambda _menu: list(state["rows"]),
        click_row_fn=click_row,
        close_menu_fn=lambda: None,
        ensure_xiadan_fn=lambda client: None,
        switch_account_fn=switch_account,
        open_row_fn=lambda _combo, _row, _total, _client: switch_account("", 0, _client),
        dialog_records_fn=lambda _client, _settings: list(state["dialogs"]),
        close_dialog_fn=close,
        screenshot_fn=lambda _name: "runtime_data/screenshots/mock.png",
        sleep_fn=lambda _seconds: None,
    ), state


def test_match_masked_text_requires_clear_second_score():
    options = [
        FundAccountRef.from_label(0, "平安证券-2234567890"),
        FundAccountRef.from_label(1, "平安证券-2234567891"),
    ]
    matched, code = match_fund_account(options, {"display_masked": "平安证券-223****789O"})
    assert code == ""
    assert matched.index == 0


def test_menu_rows_classify_login_required_and_name_rows():
    masked = FundAccountRef.from_label(0, "平安证券-3262****8611")
    name = FundAccountRef.from_label(1, "平安证券-张*龙")
    assert masked.row_kind == "login_required"
    assert masked.login_required is True
    assert masked.safe_dict()["row_kind"] == "login_required"
    assert name.row_kind == "direct"
    assert name.login_required is False


def test_discover_prioritizes_direct_name_rows_and_records_login_required():
    ui, state = _ui()
    state["rows"] = [
        {"index": 0, "text": "平安证券-3262****8611", "top": 0},
        {"index": 1, "text": "中信建投证券-许*鸣融", "top": 1},
        {"index": 2, "text": "平安证券-张*龙 F12已登录", "top": 2},
    ]
    refs = ui.discover_fund_accounts()
    assert [(ref.index, ref.row_kind) for ref in refs] == [
        (1, "direct"),
        (2, "direct"),
        (0, "login_required"),
    ]
    assert refs[-1].login_required is True


def test_masked_account_ocr_tolerates_noise_and_zero_letter_o():
    options = [FundAccountRef.from_label(0, "平安证券-2234567890")]
    matched, code = match_fund_account(options, {"display_masked": "国 平安证券-223****789O"})
    assert code == ""
    assert matched.index == 0


def test_name_row_ocr_tolerates_short_tail_noise():
    options = [FundAccountRef.from_label(0, "中信建投证券-许*鸣融")]
    matched, code = match_fund_account(options, {"display_text": "中信建投证券-许*鸣"})
    assert code == ""
    assert matched.index == 0


def test_login_required_row_records_kind_and_closes_login_popup():
    dialogs = [{"title": "委托下单", "kind": "manual", "texts": ["资金账号", "交易密码", "验证码", "登录"]}]
    ui, state = _ui(
        current="1111111111",
        labels=("平安证券-32621238611",),
        dialogs=dialogs,
        switch_value="32621238611",
    )
    state["rows"] = [{"index": 0, "text": "平安证券-3262****8611", "top": 0}]
    target = ui.discover_fund_accounts()[0]
    assert target.login_required is True
    result = ui.login_fund_account(target)
    assert result.status == "dialog_closed"
    assert result.row_kind == "login_required"
    assert result.login_required is True
    assert result.as_dict()["status"] == "dialog_closed"
    assert state["closed"] == dialogs


def test_click_failure_is_not_selected_not_ready():
    ui, _state = _ui(labels=("平安证券-张*龙",))

    def fail_click(_menu, _row, _total):
        raise AutoIpoError("MENU_CLICK_FAILED", "点击失败", "重试")

    ui._click_row_fn = fail_click
    target = ui.discover_fund_accounts()[0]
    result = ui.login_fund_account(target)
    assert result.status == "not_selected"
    assert result.error_code == "MENU_CLICK_FAILED"
    assert result.failure_stage == "menu_click"


def test_target_absent_after_click_is_not_logged_in():
    ui, _state = _ui(
        current="9999999990",
        labels=("乙-9999999990",),
        switch_value="9999999990",
    )
    state_rows = [{"index": 0, "text": "甲-****7890", "top": 0}]
    ui._read_rows_fn = lambda _menu: list(state_rows)
    target = ui.discover_fund_accounts()[0]
    result = ui.login_fund_account(target)
    assert result.status == "not_logged_in"
    assert result.error_code == "FUND_ACCOUNT_NOT_FOUND"
    assert result.failure_stage == "fund_login_result"


def test_match_masked_text_rejects_low_similarity():
    options = [FundAccountRef.from_label(0, "平安证券-2234567890")]
    matched, code = match_fund_account(options, {"display_masked": "招商证券-999****1234"})
    assert matched is None
    assert code == "FUND_ACCOUNT_NOT_FOUND"


def test_reopened_menu_uses_masked_fuzzy_match_without_cached_row_click():
    ui, state = _ui(labels=("甲证券-2234567890",))
    target = ui.discover_fund_accounts()[0]
    state["rows"] = [{"index": 0, "text": "甲证券-223****789O", "top": 0}]
    clicked = []
    ui._click_row_fn = lambda _menu, row, _total: clicked.append(row["index"])
    ui._click_main_row(target)
    assert clicked == [0]


def test_tail4_duplicate_is_ambiguous():
    options = [
        FundAccountRef.from_label(0, "甲-1234567890"),
        FundAccountRef.from_label(1, "乙-2234567890"),
    ]
    assert match_fund_account(options, {"fund_account_tail4": "7890"})[1] == "FUND_ACCOUNT_AMBIGUOUS"


def test_full_account_target_matches_only_sha256():
    options = [
        FundAccountRef.from_label(0, "甲-1234567890"),
        FundAccountRef.from_label(1, "乙-2234567890"),
    ]
    target = options[0]
    assert match_fund_account(options, {"fund_account_hash": target.fund_account_hash})[0].index == 0
    assert match_fund_account(options, {"display_text": "甲-1234567890"})[0].index == 0
    assert match_fund_account(options, {"fund_account_hash": "0" * 64})[1] == "FUND_ACCOUNT_NOT_FOUND"
    spoofed = [{"fund_account_hash": "0" * 64, "display_text": "甲-1234567890"}]
    assert match_fund_account(options, spoofed[0])[1] == "FUND_ACCOUNT_NOT_FOUND"


def test_same_account_different_labels_share_hash_identity():
    first = FundAccountRef.from_label(0, "甲-1234567890")
    second = FundAccountRef.from_label(1, "乙-1234567890")
    assert first.fund_account_hash == second.fund_account_hash
    assert first.key == second.key


def test_tail4_alone_is_not_identity_verification():
    ui, _state = _ui(current="1234567890", labels=("乙-2234567890",))
    ref = FundAccountRef.from_label(0, "甲-****7890")
    assert ui._identity_matches(ref, "1234567890", "乙-223****7890", ["乙-223****7890"]) is False


def test_discover_keeps_full_discovery_and_original_indexes():
    ui, state = _ui(labels=("编辑账户", "甲-1234567890", "乙-2234567890"))
    state["rows"] = [
        {"index": 0, "text": "编辑账户", "top": 0},
        {"index": 1, "text": "甲-1234567890", "top": 1},
        {"index": 2, "text": "乙-2234567890", "top": 2},
    ]
    state["labels"] = ["甲-1234567890", "乙-2234567890"]
    ui.cfg["execution"]["ths_account_switch"]["max_fund_accounts_per_ths"] = 1
    refs = ui.discover_fund_accounts()
    assert [ref.index for ref in refs] == [1, 2]


def test_menu_click_uses_one_open_snapshot():
    state = {"open": 0, "read": 0, "click": 0, "menu": None}

    def open_menu():
        state["open"] += 1
        state["menu"] = object()
        return state["menu"]

    def read_rows(menu):
        assert menu is state["menu"]
        state["read"] += 1
        return [{"index": 0, "text": "甲-1234567890", "top": 0}]

    def click_row(menu, row, total):
        assert menu is state["menu"]
        assert (row["index"], total) == (0, 1)
        state["click"] += 1

    ui = ThsAccountUI(
        client=object(),
        cfg=_cfg(),
        open_menu_fn=open_menu,
        read_rows_fn=read_rows,
        click_row_fn=click_row,
        close_menu_fn=lambda: None,
        current_value_fn=lambda _client: "1234567890",
        main_window_fn=lambda _client: FakeMain([]),
        ensure_xiadan_fn=lambda client: None,
        screenshot_fn=lambda _name: "mock.png",
    )
    ref = FundAccountRef.from_label(0, "甲-1234567890")
    ui._click_main_row(ref)
    assert (state["open"], state["read"], state["click"]) == (1, 1, 1)


def test_xiadan_dropdown_filtering_preserves_original_index():
    ui, _state = _ui()
    combo = FakeControl(2322, items=["编辑账户", "甲-1234567890", "乙-223****7890"])
    calls = []
    ui._main_window_fn = lambda _client: FakeMain([combo])
    ui._open_row_fn = lambda _combo, row, total, _client: calls.append((row, total))
    target = FundAccountRef.from_label(0, "乙-223****7890")
    ui._switch_xiadan_target(target)
    assert calls == [(2, 3)]


def test_unique_configured_control_is_required():
    ui, _state = _ui()
    main = FakeMain([FakeControl(2322, items=["甲"]), FakeControl(2322, items=["乙"])])
    with pytest.raises(AutoIpoError) as exc:
        ui._require_unique_combo(main, 2322, "account_combo_control_id")
    assert exc.value.code == "THS_CONTROL_ID_NOT_UNIQUE"


def test_xiadan_identity_reenumerates_once_after_stale_handle():
    ui, _state = _ui()
    calls = []

    def main(_client):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("Handle 12345 is not a valid window handle")
        return FakeMain([
            FakeControl(1711, "1234567890"),
            FakeControl(2322, "平安证券-1234567890", ["平安证券-1234567890"]),
        ])

    ui._main_window_fn = main
    ui._sleep = lambda _seconds: None

    present, current, _display, labels = ui._xiadan_identity()
    assert len(calls) == 2
    assert present is True
    assert current == "1234567890"
    assert labels == ["平安证券-1234567890"]


def test_unique_configured_combo_does_not_use_legacy_combo_guard(monkeypatch):
    from execution import login

    def fail(_client=None):
        raise AutoIpoError(
            "XIADAN_ACCOUNT_COMBO_INVALID",
            "legacy guard must not run",
            "use gui.xiadan.account_combo_control_id",
        )

    monkeypatch.setattr(login, "_account_combo", fail)
    monkeypatch.setattr(login, "logged_in_labels", fail)
    ui, _state = _ui(current="1111111111", switch_value="1234567890")
    target = ui.discover_fund_accounts()[0]
    result = ui.login_fund_account(target)
    assert result.status == "ready"
    assert result.error_code == ""


def test_direct_login_verifies_hash_and_visible_xiadan_list():
    ui, state = _ui(current="1111111111", labels=("平安证券-1234567890",), switch_value="1234567890")
    target = ui.discover_fund_accounts()[0]
    result = ui.login_fund_account(target)
    assert result.status == "ready"
    assert result.xiadan_present is True
    assert result.fund_account_hash == target.fund_account_hash
    assert state["closed"] == []


def test_fund_login_password_captcha_dialog_is_closed_and_continues():
    dialogs = [{"title": "委托下单", "kind": "login", "texts": ["资金账号", "交易密码", "验证码"]}]
    ui, state = _ui(
        current="1111111111",
        labels=("平安证券-1234567890",),
        dialogs=dialogs,
        switch_value="1234567890",
    )
    target = ui.discover_fund_accounts()[0]
    result = ui.login_fund_account(target)
    assert result.status in {"dialog_required", "dialog_closed"}
    assert result.dialog_required is True
    assert result.manual_required is False
    assert state["closed"] == dialogs
    assert state["dialogs"] == []
    assert ui._ths_stop_reason == ""
    second = ui.login_fund_account(target)
    assert second.status == "ready"
    assert second.manual_required is False


def test_fund_login_dialog_detected_by_window_structure_not_keyword():
    dialogs = [
        {
            "title": "委托下单",
            "kind": "manual",
            "texts": ["资金账号", "交易密码", "验证码", "安全验证", "随机校验码"],
        }
    ]
    ui, state = _ui(
        current="1111111111",
        labels=("平安证券-1234567890",),
        dialogs=dialogs,
        switch_value="1234567890",
    )
    target = ui.discover_fund_accounts()[0]
    result = ui.login_fund_account(target)
    assert result.status in {"dialog_required", "dialog_closed"}
    assert result.dialog_required is True
    assert result.manual_required is False
    assert state["closed"] == dialogs
    assert state["dialogs"] == []


def test_kind_login_wins_over_security_keywords_without_form_structure():
    dialogs = [{"title": "安全验证", "kind": "login", "texts": ["验证码", "安全验证"]}]
    ui, state = _ui(
        current="1111111111",
        dialogs=dialogs,
        switch_value="1234567890",
    )
    target = ui.discover_fund_accounts()[0]
    result = ui.login_fund_account(target)
    assert result.status in {"dialog_required", "dialog_closed"}
    assert result.dialog_required is True
    assert result.manual_required is False
    assert state["closed"] == dialogs


def test_manual_captcha_dialog_is_not_closed_and_stops_ths():
    dialogs = [{"title": "安全验证", "kind": "manual", "texts": ["验证码"]}]
    ui, state = _ui(
        current="1111111111",
        labels=("平安证券-1234567890",),
        dialogs=dialogs,
        switch_value="1234567890",
    )
    target = ui.discover_fund_accounts()[0]
    result = ui.login_fund_account(target)
    assert result.status == "manual_required"
    assert result.manual_required is True
    assert state["closed"] == []
    assert state["dialogs"] == dialogs
    blocked = ui.login_fund_account(target)
    assert blocked.status == "manual_required"
    assert state["switch_calls"] == []


def test_dialog_cleanup_failure_returns_error_and_stops_ths():
    dialogs = [{"title": "委托下单", "kind": "login", "texts": ["资金账号", "交易密码"]}]
    ui, state = _ui(
        current="1111111111",
        labels=("平安证券-1234567890",),
        dialogs=dialogs,
        switch_value="1234567890",
    )
    state["close"] = lambda records, _settings, _client: False
    target = ui.discover_fund_accounts()[0]
    result = ui.login_fund_account(target)
    assert result.status == "dialog_cleanup_failed"
    assert result.error_code == "dialog_cleanup_failed"
    assert state["dialogs"] == dialogs
    blocked = ui.login_fund_account(target)
    assert blocked.status == "dialog_cleanup_failed"
    assert state["switch_calls"] == []


def test_wrong_current_account_is_structured():
    ui, _state = _ui(
        current="1111111111",
        labels=("平安证券-1234567890",),
        switch_value="9999999999",
    )
    target = ui.discover_fund_accounts()[0]
    result = ui.login_fund_account(target)
    assert result.status == "wrong_account"
    assert result.fund_account_hash == target.fund_account_hash


def test_close_main_window_requires_unique_main_window():
    class FakeWindow:
        def __init__(self, title, class_name="Afx:00400000"):
            self.title = title
            self._class_name = class_name
            self.closed = False

        def window_text(self):
            return self.title

        def class_name(self):
            return self._class_name

        def close(self):
            self.closed = True

    main = FakeWindow("同花顺")
    popup = FakeWindow("切换账号", "#32770")
    ui = HexinSwitchUI(client=object(), cfg={"gui": {"ths_account_switch": {}}})
    ui._windows = lambda visible_only=True: [main, popup]
    ui.close_main_window()
    assert main.closed is True
    assert popup.closed is False

    other = FakeWindow("同花顺二")
    ui._windows = lambda visible_only=True: [main, other]
    with pytest.raises(AutoIpoError) as exc:
        ui.close_main_window()
    assert exc.value.code == "THS_MAIN_WINDOW_NOT_UNIQUE"

class FakeSwitchControl:
    def __init__(self, text):
        self._text = text

    def window_text(self):
        return self._text


class FakeSwitchWindow:
    def __init__(self, title, texts):
        self._title = title
        self._texts = list(texts)

    def window_text(self):
        return self._title

    def descendants(self, class_name=""):
        return [FakeSwitchControl(text) for text in self._texts]


def _switch_ui(texts, known=("mx_525378109", "mx_mbqdpecj9"), command_line_fn=None):
    ui = HexinSwitchUI(
        client=object(),
        cfg={"gui": {"ths_account_switch": {}}},
        known_ths_accounts=list(known),
        command_line_fn=command_line_fn,
    )
    ui._windows = lambda visible_only=True: [FakeSwitchWindow("同花顺(9.60.71) - 自选股", texts)]
    return ui


# RED: 登录窗账号 ComboBox 的当前显示值直接作为 THS username，禁止 OCR。
def test_current_account_name_uses_login_combo_selection_without_ocr():
    class Combo:
        def window_text(self):
            return "mx_525378109"

        def item_texts(self):
            return ["mx_525378109", "mx_mbqdpecj9"]

    class LoginWindow:
        def window_text(self):
            return "同花顺登录"

        def descendants(self, class_name=""):
            if class_name == "ComboBox":
                return [Combo()]
            if class_name == "Button":
                return [FakeSwitchControl("登录")]
            return [FakeSwitchControl("")]

    ui = _switch_ui([], known=("mx_525378109", "mx_mbqdpecj9"))
    window = LoginWindow()
    ui._windows = lambda visible_only=True: [window]
    ui._login_window = lambda: window
    ui._username_ocr_fn = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("OCR must not run")
    )

    assert ui.current_account_name() == "mx_525378109"


def test_wait_for_main_window_ignores_login_combo_selection(monkeypatch):
    ui = _switch_ui([], known=("mx_525378109",))
    ui._main_window = lambda: None
    ui._login_window = lambda: object()
    ui.current_account_name = lambda: "mx_525378109"
    ui._sleep = lambda _seconds: None
    values = iter([0.0, 0.0, 2.0])
    monkeypatch.setattr("execution.ths_account_windows.time.monotonic", lambda: next(values))

    assert ui.wait_for_main_window(1) is False


def test_wait_for_main_window_requires_real_main_window(monkeypatch):
    ui = _switch_ui([], known=("mx_525378109",))
    ui._main_window = lambda: object()
    ui.current_account_name = lambda: (_ for _ in ()).throw(AssertionError("not needed"))
    values = iter([0.0, 0.0])
    monkeypatch.setattr("execution.ths_account_windows.time.monotonic", lambda: next(values))

    assert ui.wait_for_main_window(1) is True

def test_current_account_name_reads_visible_control_texts():
    ui = _switch_ui(["自选股", "行情", "mx_525378109"])
    assert ui.current_account_name() == "mx_525378109"


def test_current_account_name_accepts_visible_username_token():
    ui = _switch_ui(["当前用户：mx_mbqdpecj9"], known=("mx_525378109",))
    assert ui.current_account_name() == "mx_mbqdpecj9"


def test_current_account_name_uses_command_line_without_leaking_hash():
    secret = "cmd-token-SUPERSECRET-9f8e7d6c"
    ui = _switch_ui(
        ["自选股"],
        known=("mx_525378109",),
        command_line_fn=lambda _pids: [f"hexin.exe mx_525378109 --token {secret}"],
    )
    assert ui.current_account_name() == "mx_525378109"


def test_current_account_name_retries_read_after_invalid_window():
    state = {"windows": 0, "reads": 0}
    ui = _switch_ui(["mx_525378109"], known=("mx_525378109",))

    def windows(visible_only=True):
        state["windows"] += 1
        return [FakeSwitchWindow("同花顺(9.60.71) - 自选股", ["mx_525378109"])]

    def visible_texts(_window):
        state["reads"] += 1
        if state["reads"] == 1:
            raise RuntimeError("Handle 12345 is not a valid window handle")
        return ["mx_525378109"]

    ui._windows = windows
    ui._visible_texts_fn = visible_texts
    assert ui.current_account_name() == "mx_525378109"
    assert state == {"windows": 4, "reads": 2}


def test_current_account_name_retry_failure_is_safe_structured_error():
    secret = "sensitive-window-token-9f8e7d6c"
    ui = _switch_ui(["自选股"], known=("mx_525378109",))
    ui._visible_texts_fn = lambda _window: (_ for _ in ()).throw(
        RuntimeError(f"Handle 4242 {secret} is not a valid window handle")
    )
    with pytest.raises(AutoIpoError) as exc:
        ui.current_account_name()
    assert exc.value.code == "THS_CURRENT_ACCOUNT_UNREADABLE"
    rendered = str(exc.value) + json.dumps(exc.value.as_dict(), ensure_ascii=False)
    assert "4242" not in rendered
    assert secret not in rendered


def test_command_line_unknown_tokens_and_hashes_never_leak():
    secret = "hash-abcdef0123456789"
    ui = _switch_ui(
        ["自选股"],
        known=("mx_525378109",),
        command_line_fn=lambda _pids: [f"hexin.exe mx_unknownuser99 --token {secret}"],
    )
    with pytest.raises(AutoIpoError) as exc:
        ui.current_account_name()
    assert exc.value.code == "THS_CURRENT_ACCOUNT_UNREADABLE"
    text = str(exc.value) + json.dumps(exc.value.as_dict(), ensure_ascii=False)
    assert secret not in text
    assert "mx_unknownuser99" not in text


def test_close_main_window_posts_wm_close_without_waiting(monkeypatch):
    import sys
    import types

    posted = []

    class FakeWindow:
        def __init__(self, title, handle):
            self._title = title
            self.handle = handle
            self.closed = False

        def window_text(self):
            return self._title

        def class_name(self):
            return "Afx:00400000"

        def close(self):
            self.closed = True

    fake_gui = types.ModuleType("win32gui")
    fake_gui.PostMessage = lambda hwnd, msg, _w, _l: posted.append((hwnd, msg))
    monkeypatch.setitem(sys.modules, "win32gui", fake_gui)

    main = FakeWindow("同花顺(9.60.71) - 自选股", 123)
    ui = HexinSwitchUI(client=object(), cfg={"gui": {"ths_account_switch": {}}})
    ui._windows = lambda visible_only=True: [main]
    ui.close_main_window()
    assert posted == [(123, 0x0010)]
    assert main.closed is False

def test_popup_button_matches_accelerator_suffix():
    window = FakeSwitchWindow("提示", [])
    button = FakeSwitchControl("退出(&X)")
    window.descendants = lambda class_name="": [button] if class_name in ("", "Button") else []
    ui = HexinSwitchUI(client=object(), cfg={"gui": {"ths_account_switch": {}}})
    assert ui._button(window, "退出") is button


class FakePasswordEdit:
    def __init__(self, control_id, style, handle, has_text):
        self.element_info = types.SimpleNamespace(control_id=control_id, handle=handle)
        self.handle = handle
        self._control_id = control_id
        self._style = style
        self._has_text = has_text
        self.writes = []

    def is_visible(self):
        return True

    def rectangle(self):
        return types.SimpleNamespace(left=1, top=2, right=31, bottom=32)

    def set_edit_text(self, value):
        self.writes.append(value)


def _password_ui(monkeypatch, edits):
    import sys
    import types

    fake_gui = types.ModuleType("win32gui")
    fake_gui.GetWindowLongW = lambda handle, _index: next(
        edit._style for edit in edits if edit.handle == handle
    )
    fake_gui.GetWindowTextLength = lambda handle: int(next(
        edit._has_text for edit in edits if edit.handle == handle
    ))
    monkeypatch.setitem(sys.modules, "win32gui", fake_gui)
    window = types.SimpleNamespace(
        descendants=lambda class_name="": edits if class_name == "Edit" else []
    )
    ui = HexinSwitchUI(client=object(), cfg={"gui": {"ths_account_switch": {}}})
    ui._login_window = lambda: window
    return ui


def test_password_control_selects_es_password_without_reading_text(monkeypatch):
    username = FakePasswordEdit(101, 0x0080, 101, True)
    password = FakePasswordEdit(202, 0x0020, 202, True)
    ui = _password_ui(monkeypatch, [username, password])

    assert ui.password_has_text() is True
    assert username.writes == []


def test_password_control_writes_only_selected_password_edit(monkeypatch):
    username = FakePasswordEdit(101, 0x0080, 101, True)
    password = FakePasswordEdit(202, 0x0020, 202, False)
    ui = _password_ui(monkeypatch, [username, password])

    assert ui.password_has_text() is False
    ui.set_password("fake-password")
    assert username.writes == []
    assert password.writes == ["fake-password"]


# RED: 真实自绘控件可能没有 Win32 handle/control_id，但仍应凭 style/rectangle 安全选中密码框。
def test_password_metadata_accepts_missing_handle_and_control_id(monkeypatch):
    class HeadlessPasswordEdit(FakePasswordEdit):
        def __init__(self):
            super().__init__(-1, 0x0020, 0, False)
            self.element_info = types.SimpleNamespace(control_id=-1, handle=0)

        def style(self):
            return self._style

        def control_id(self):
            return -1

    edit = HeadlessPasswordEdit()
    ui = _password_ui(monkeypatch, [edit])

    assert ui.password_has_text() is False
    ui.set_password("fake-password")
    assert edit.writes == ["fake-password"]


# RED: style 不可见时必须只接受控件提供的密码提示，不读取 Edit 文本。
def test_password_metadata_uses_password_hint_when_style_missing(monkeypatch):
    class HintedPasswordEdit:
        is_password = True
        handle = 0

        def __init__(self):
            self.element_info = types.SimpleNamespace(control_id=-1, handle=0, is_password=True)
            self.writes = []

        def is_visible(self):
            return True

        def rectangle(self):
            return types.SimpleNamespace(left=2, top=3, right=42, bottom=33)

        def set_edit_text(self, value):
            self.writes.append(value)

    edit = HintedPasswordEdit()
    ui = _password_ui(monkeypatch, [edit])

    assert ui.password_has_text() is False
    ui.set_password("fake-password")
    assert edit.writes == ["fake-password"]

def test_late_fund_login_dialog_is_closed_before_wrong_account():
    ui, _state = _ui(current="1111111111", labels=("\u5e73\u5b89\u8bc1\u5238-3262****8611",), switch_value="2222222222")
    target = ui.discover_fund_accounts()[0]
    calls = {"count": 0, "visible": True}
    login_row = {
        "hwnd": 123,
        "title": "\u59d4\u6258\u4e0b\u5355",
        "kind": "login",
        "texts": ["\u8d44\u91d1\u8d26\u53f7", "\u4ea4\u6613\u5bc6\u7801", "\u9a8c\u8bc1\u7801", "\u767b\u5f55"],
    }

    def records(_client, _settings):
        calls["count"] += 1
        return [login_row] if calls["count"] >= 3 and calls["visible"] else []

    def close(_records, _settings, _client):
        calls["visible"] = False
        return True

    ui._dialog_records_fn = records
    ui._close_login_dialog_fn = close
    ui._sleep = lambda _seconds: None

    result = ui.login_fund_account(target)

    assert result.status == "dialog_closed"
    assert calls["visible"] is False

# RED: 无元数据的非密码 Edit 不得阻断有效密码框识别。
# RED: 登录窗 Edit 元数据失败必须留下安全诊断，不得包含控件文本或密码值。
def test_password_metadata_failure_writes_safe_diagnostics(monkeypatch, tmp_path):
    import json

    class BrokenEdit:
        handle = 0
        _style = 0

        def is_visible(self):
            return True

    monkeypatch.setattr(
        "shared.paths.runtime_path",
        lambda *parts: tmp_path.joinpath(*parts),
    )
    ui = _password_ui(monkeypatch, [BrokenEdit()])

    with pytest.raises(AutoIpoError):
        ui.password_edit_controls()

    payload = json.loads(
        (tmp_path / "diagnostics" / "password_edit_metadata.json").read_text(encoding="utf-8")
    )
    raw = json.dumps(payload, ensure_ascii=False)
    assert payload["invalid_rows"]
    assert payload["invalid_rows"][0]["stage"]
    assert "text" not in raw
    assert "value" not in raw
    assert "password" not in raw.lower()
    assert "fund_account" not in raw.lower()

def test_invalid_non_password_edit_does_not_block_password_selection(monkeypatch):
    class BrokenEdit:
        handle = 0

        def is_visible(self):
            return True

    username = FakePasswordEdit(101, 0x0080, 101, True)
    password = FakePasswordEdit(202, 0x0020, 202, True)
    ui = _password_ui(monkeypatch, [BrokenEdit(), username, password])

    assert ui.password_has_text() is True
    assert username.writes == []
    assert password.writes == []

def test_password_metadata_falls_back_to_control_id_method(monkeypatch):
    username = FakePasswordEdit(101, 0x0080, 101, True)
    password = FakePasswordEdit(202, 0x0020, 202, True)
    for edit, cid in ((username, 101), (password, 202)):
        edit.element_info = types.SimpleNamespace(handle=edit.handle)
        edit.control_id = lambda value=cid: value
    ui = _password_ui(monkeypatch, [username, password])

    assert ui.password_has_text() is True
    assert username.writes == []
# RED: 自绘资金账户登录框可能缺少“资金账号”标签，按证券公司+交易密码+登录结构仍须关闭。
def test_partial_self_drawn_fund_login_row_is_closed():
    dialogs = [{
        "title": "",
        "kind": "",
        "texts": ["证券公司:", "交易密码:", "短信验证码:", "登录"],
    }]
    ui, state = _ui(
        current="1111111111",
        labels=("平安证券-1234567890",),
        dialogs=dialogs,
        switch_value="1234567890",
    )
    target = ui.discover_fund_accounts()[0]
    result = ui.login_fund_account(target)

    assert result.status == "dialog_closed"
    assert result.manual_required is False
    assert state["closed"] == dialogs
    assert state["dialogs"] == []
# RED: 目标只出现在 xiadan 下拉列表不能判 ready。
def test_dropdown_membership_alone_is_not_ready():
    ui, state = _ui(
        current="1111111111",
        labels=("平安证券-张*龙", "平安证券-陈*燕"),
        switch_value="1111111111",
    )
    state["rows"] = [{"index": 0, "text": "平安证券-陈*燕", "top": 0}]
    target = ui.discover_fund_accounts()[0]
    result = ui.login_fund_account(target)
    assert result.status == "wrong_account"
    assert result.error_code == "FUND_ACCOUNT_VERIFY_FAILED"
    assert result.identity_verified_by == ""


# RED: 姓名行可由当前账户显示名复核。
def test_name_row_ready_by_current_account_display_name():
    ui, state = _ui(
        current="1111111111",
        labels=("平安证券-张*龙",),
        switch_value="1111111111",
    )
    state["rows"] = [{"index": 0, "text": "平安证券-张*龙", "top": 0}]
    target = ui.discover_fund_accounts()[0]
    result = ui.login_fund_account(target)
    assert result.status == "ready"
    assert result.identity_verified_by == "display_name"


# RED: 掩码资金账号行可由当前资金账号脱敏值复核。
def test_masked_row_ready_by_current_fund_account():
    ui, state = _ui(
        current="32621238611",
        labels=("平安证券-3262****8611",),
        switch_value="32621238611",
    )
    state["rows"] = [{"index": 0, "text": "平安证券-3262****8611", "top": 0}]
    target = ui.discover_fund_accounts()[0]
    result = ui.login_fund_account(target)
    assert result.status == "ready"
    assert result.identity_verified_by == "masked_account"


# RED: 切户异常必须记 switch_failed，不得吞掉后误报 wrong_account。
def test_switch_failure_is_recorded_separately():
    ui, state = _ui(
        current="1111111111",
        labels=("平安证券-张*龙",),
        switch_value="1111111111",
    )
    state["rows"] = [{"index": 0, "text": "平安证券-陈*燕", "top": 0}]
    target = ui.discover_fund_accounts()[0]

    def fail_switch(_target):
        raise AutoIpoError("FUND_ACCOUNT_SWITCH_FAILED", "切户失败", "重试")

    ui._switch_xiadan_target = fail_switch
    result = ui.login_fund_account(target)
    assert result.status == "switch_failed"
    assert result.error_code == "FUND_ACCOUNT_SWITCH_FAILED"
    assert result.failure_stage == "xiadan_switch"


# RED: wrong_account 必须留下脱敏观察值和失败阶段。
def test_wrong_account_records_safe_observation_and_stage():
    ui, _state = _ui(
        current="1111111111",
        labels=("平安证券-张*龙", "平安证券-陈*燕"),
        switch_value="1111111111",
    )
    ui._read_rows_fn = lambda _menu: [
        {"index": 0, "text": "平安证券-陈*燕", "top": 0}
    ]
    target = ui.discover_fund_accounts()[0]
    result = ui.login_fund_account(target)
    assert result.status == "wrong_account"
    assert result.failure_stage == "identity_verify"
    assert result.observed_current_masked == "****1111"
    assert result.observed_display_masked == "平安证券-张*龙"
    assert "1111111111" not in str(result.as_dict())




def test_target_missing_from_xiadan_stays_not_logged_in():
    ui, state = _ui(
        current="1111111111",
        labels=("平安证券-张*龙",),
        switch_value="1111111111",
    )
    state["rows"] = [{"index": 0, "text": "平安证券-陈*燕", "top": 0}]
    target = ui.discover_fund_accounts()[0]

    def missing(_target):
        raise AutoIpoError(
            "XIADAN_ACCOUNT_NOT_FOUND",
            "账户下拉中没有目标账户",
            "先登录目标账户",
        )

    ui._switch_xiadan_target = missing
    result = ui.login_fund_account(target)

    assert result.status == "not_logged_in"
    assert result.login_status == "not_logged_in"
    assert result.error_code == "FUND_ACCOUNT_NOT_FOUND"
    assert result.failure_stage == "fund_login_result"


def test_login_result_contains_menu_click_diagnostics():
    ui, state = _ui(
        current="1234567890",
        labels=("甲-1234567890",),
        switch_value="1234567890",
    )
    state["rows"] = [{
        "index": 3,
        "text": "甲-1234567890",
        "left": 100,
        "top": 20,
        "right": 260,
        "bottom": 46,
        "click_x": 180,
        "click_y": 33,
        "source": "ocr",
    }]
    target = ui.discover_fund_accounts()[0]
    result = ui.login_fund_account(target).as_dict()

    assert result["menu_row_index"] == 3
    assert result["clicked_x"] == 180
    assert result["clicked_y"] == 33
    assert result["menu_row_rect"] == [100, 20, 260, 46]
    assert result["menu_source"] == "ocr"
    assert result["xiadan_labels_masked"] == ["甲-123****7890"]


def test_login_dialog_is_screenshotted_before_close():
    events = []
    dialog = {"title": "委托下单", "kind": "login", "texts": ["资金账号", "交易密码"]}
    ui, state = _ui(current="1111111111", labels=("甲-1111111111",), dialogs=[dialog])
    state["rows"] = [{"index": 0, "text": "乙-2222222222", "top": 0}]
    def close_dialog(_records, _settings, _client):
        events.append("close")
        state["dialogs"] = []
        return True

    state["close"] = close_dialog
    ui._click_row_fn = lambda _menu, _row, _total: None
    ui._screenshot_fn = lambda name: events.append(f"screenshot:{name}")

    result = ui.login_fund_account(ui.discover_fund_accounts()[0])

    assert result.status == "dialog_closed"
    assert events[0].startswith("screenshot:fund_login/")
    assert events[1].endswith("_after_fill.png")  # 自动填充尝试后留证
    assert events[2] == "close"
    assert result.as_dict().get("auto_fill")  # 失败原因已落盘



def test_closed_login_dialog_can_finish_target_login():
    events = []
    dialog = {"title": "委托下单", "kind": "login", "texts": ["资金账号", "交易密码"]}
    ui, state = _ui(
        current="1111111111",
        labels=("甲-1111111111",),
        dialogs=[dialog],
        switch_value="2222222222",
    )
    state["rows"] = [{"index": 0, "text": "乙-2222222222", "top": 0}]

    def close_dialog(_records, _settings, _client):
        events.append("close")
        state["dialogs"] = []
        state["current"] = "2222222222"
        state["labels"] = ["乙-2222222222"]
        return True

    state["close"] = close_dialog
    ui._click_row_fn = lambda _menu, _row, _total: None
    ui._screenshot_fn = lambda name: events.append(f"screenshot:{name}")

    result = ui.login_fund_account(ui.discover_fund_accounts()[0])

    assert result.status == "ready"
    assert result.identity_verified_by in {"display_name", "masked_account", "fund_account_hash"}
    assert events[0].startswith("screenshot:fund_login/")
    assert events[1].endswith("_after_fill.png")
    assert events[2] == "close"



def test_credit_authentication_form_is_fund_login_dialog():
    row = {
        "title": "止盈止损 信用交易认证",
        "kind": "",
        "texts": ["请输入信用交易认证信息", "帐 号(A):", "认证密码(G):", "保存帐户", "确定", "取消"],
    }
    ui = ThsAccountUI(client=object(), cfg=_cfg())

    assert ui._is_fund_login_row(row) is True
    assert ui._manual_dialog_rows([row]) == []



def test_display_identity_normalizes_ocr_separator_noise_for_identity():
    ui = ThsAccountUI(client=object(), cfg=_cfg())
    ref = FundAccountRef.from_label(0, "国 平安证券一许*峰")

    assert ui._identity_source(ref, "", "平安证券-许*峰") == "display_name"
def test_fund_account_deadline_raises_timeout(monkeypatch):
    """单户硬限时：_sleep 到点抛 FUND_ACCOUNT_TIMEOUT，不再空等。"""
    from shared.errors import AutoIpoError
    from execution.ths_account_ui import ThsAccountUI

    ui = ThsAccountUI(client=object(), cfg={}, sleep_fn=lambda _s: None)
    ui.start_deadline(0.05)
    import time as _time
    _time.sleep(0.06)
    try:
        ui._sleep(5.0)
    except AutoIpoError as exc:
        assert exc.code == "FUND_ACCOUNT_TIMEOUT"
    else:
        raise AssertionError("应抛 FUND_ACCOUNT_TIMEOUT")
    ui.clear_deadline()
    ui._sleep(0.0)  # 清除后不再抛


def test_fund_account_deadline_bounds_sleep_duration(monkeypatch):
    """deadline 内的 sleep 被截断到剩余时间，不会睡过头。"""
    from execution.ths_account_ui import ThsAccountUI

    slept = []
    ui = ThsAccountUI(client=object(), cfg={}, sleep_fn=lambda s: slept.append(s))
    ui.start_deadline(30)
    ui._sleep(5.0)
    assert slept == [5.0]
    ui._sleep(1e9)  # 远超剩余限时 → 截断为剩余 ≈30s（fake sleep 不耗墙钟），不抛异常
    assert 25.0 <= slept[1] <= 30.0
    ui.clear_deadline()
