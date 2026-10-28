# AI-SUMMARY: 同花顺登录账户切换核心状态机测试——纯 mock，覆盖密码控件选择、登录路径、歧义与脱敏
import json
import sys
from types import SimpleNamespace

import pytest

from shared.errors import AutoIpoError
from execution.ths_account_switch import (
    ThsLoginAccount,
    close_ths_client,
    select_next_account,
    select_password_edit,
    switch_ths_account,
)


class FakeUI:
    def __init__(self, *, current="", options=(), password_text="", popup=True,
                 login_window=True, main_window=True, click_popup=True,
                 login_sets_current=True, client_exited=True):
        self.current = current
        self.options = list(options)
        self.password_text = password_text
        self.popup = popup
        self.login_window = login_window
        self.main_window = main_window
        self.click_popup_result = click_popup
        self.login_sets_current = login_sets_current
        self.client_exited = client_exited
        self.events = []
        self.shots = []
        self.set_password_calls = []

    def current_account_name(self):
        self.events.append("current_account_name")
        return self.current

    def close_main_window(self):
        self.events.append("close_main_window")

    def wait_for_popup(self, timeout_s, action="切换账号"):
        self.events.append(("wait_for_popup", action))
        return self.popup

    def wait_for_client_exit(self, timeout_s):
        self.events.append("wait_for_client_exit")
        return self.client_exited

    def click_popup(self, action):
        self.events.append(("click_popup", action))
        return self.click_popup_result

    def wait_for_login_window(self, timeout_s):
        self.events.append(("wait_for_login_window", timeout_s))
        return self.login_window

    def open_account_dropdown(self):
        self.events.append("open_account_dropdown")

    def account_display_names(self):
        self.events.append("account_display_names")
        return list(self.options)

    def select_account(self, username):
        self.events.append(("select_account", username))
        self.current = username

    def password_has_text(self):
        self.events.append("password_has_text")
        return bool(self.password_text)

    def set_password(self, password):
        self.events.append("set_password")
        self.set_password_calls.append(password)
        self.password_text = password

    def click_login(self):
        self.events.append("click_login")
        if self.login_sets_current and self.options:
            self.current = self.options[0]

    def wait_for_main_window(self, timeout_s):
        self.events.append(("wait_for_main_window", timeout_s))
        return self.main_window

    def save_screenshot(self, name):
        self.events.append(("save_screenshot", name))
        self.shots.append(name)
        return f"runtime_data/screenshots/{name}"


class ControlAwareFakeUI(FakeUI):
    def __init__(self, controls, *, filled, **kwargs):
        super().__init__(**kwargs)
        self.controls = list(controls)
        self.filled = filled
        self.password_control_reads = []
        self.password_control_writes = []

    def password_edit_controls(self):
        self.events.append("password_edit_controls")
        return list(self.controls)

    def password_control_filled(self, control):
        self.events.append(("password_control_filled", control.control_id))
        self.password_control_reads.append(control)
        return self.filled

    def set_password_control(self, control, password):
        self.events.append(("set_password_control", control.control_id))
        self.password_control_writes.append((control, password))
        self.filled = True


def account(username):
    return ThsLoginAccount(username=username)


def edit(control_id, *, style=0x0080, top=10, visible=True):
    return {
        "control_id": control_id,
        "style": style,
        "rectangle": {
            "left": 10,
            "top": top,
            "right": 140,
            "bottom": top + 24,
        },
        "visible": visible,
    }


def test_ths_login_account_has_only_client_display_username():
    assert tuple(ThsLoginAccount.__dataclass_fields__) == ("username",)
    assert account("mx_1").username == "mx_1"


def test_select_next_account_uses_enabled_config_order_and_limit():
    configured = [
        {"username": "甲", "enabled": True},
        {"username": "停用", "enabled": False},
        {"username": "乙", "enabled": True},
    ]
    assert select_next_account(None, configured).username == "甲"
    assert select_next_account("甲", configured).username == "乙"
    assert select_next_account("乙", configured) is None
    assert select_next_account("外部当前", configured).username == "甲"
    assert select_next_account("甲", configured, enabled_limit=1) is None


def test_select_next_account_rejects_more_than_ten_enabled_accounts():
    configured = [account(f"户{i}") for i in range(11)]
    with pytest.raises(AutoIpoError) as exc:
        select_next_account(None, configured)
    assert exc.value.code == "THS_ACCOUNT_LIMIT_EXCEEDED"


def test_select_password_edit_uses_password_style_and_stable_metadata():
    selected = select_password_edit([
        edit(1001, top=10),
        edit(1002, style=0x0020, top=44),
    ])

    assert selected.control_id == 1002
    assert selected.style == 0x0020
    assert selected.rectangle == (10, 44, 140, 68)
    assert selected.visible is True


def test_select_password_edit_rejects_ambiguous_password_controls():
    with pytest.raises(AutoIpoError) as exc:
        select_password_edit([
            edit(1001, style=0x0020, top=10),
            edit(1002, style=0x0022, top=44),
        ])

    assert exc.value.code == "THS_PASSWORD_CONTROL_AMBIGUOUS"
    assert exc.value.as_dict()["context"]["candidate_count"] == 2


def test_select_password_edit_reports_missing_password_control():
    with pytest.raises(AutoIpoError) as exc:
        select_password_edit([edit(1001), edit(1002, visible=False)])

    assert exc.value.code == "THS_PASSWORD_CONTROL_NOT_FOUND"


def test_password_control_metadata_rejects_text_and_value_without_leaking():
    secret = "mock-secret-must-not-leak"
    with pytest.raises(AutoIpoError) as exc:
        select_password_edit([
            edit(1001, style=0x0020) | {"text": secret, "value": secret},
        ])

    assert exc.value.code == "THS_PASSWORD_CONTROL_METADATA_INVALID"
    assert secret not in str(exc.value)
    assert secret not in json.dumps(exc.value.as_dict(), ensure_ascii=False)


class RawPasswordControl:
    def __init__(self, control_id=0, handle=0):
        self.handle = handle
        self._control_id = control_id

    def control_id(self):
        return self._control_id

    def is_visible(self):
        return True

    def rectangle(self):
        return SimpleNamespace(left=10, top=44, right=140, bottom=68)

    def window_text(self):
        raise AssertionError("Edit 文本不得被读取")

    def texts(self):
        raise AssertionError("Edit 文本不得被读取")


class StalePasswordControl:
    handle = 5001

    def control_id(self):
        raise RuntimeError("Handle 5001 is not a vaild window handle")

    def is_visible(self):
        return True

    def rectangle(self):
        raise RuntimeError("Handle 5001 is not a vaild window handle")


def test_select_password_edit_uses_control_id_method_without_element_info():
    selected = select_password_edit([
        {"control": RawPasswordControl(control_id=7002, handle=5002),
            "style": 0x0020,
            "rectangle": (10, 44, 140, 68),
            "visible": True,
        },
    ])

    assert selected.control_id == 7002
    assert selected.rectangle == (10, 44, 140, 68)


def test_select_password_edit_uses_get_dlg_ctrl_id_without_element_info(monkeypatch):
    monkeypatch.setitem(sys.modules, "win32gui", SimpleNamespace(
        GetDlgCtrlID=lambda handle: 7102,
        GetWindowLongW=lambda handle, index: 0x0020,
    ))

    selected = select_password_edit([
        {
            "handle": 5003,
            "style": 0x0020,
            "rectangle": (10, 44, 140, 68),
            "visible": True,
        },
    ])

    assert selected.control_id == 7102


def test_select_password_edit_never_reads_edit_text_or_value():
    selected = select_password_edit([
        {"control": RawPasswordControl(control_id=7004, handle=5004),
            "style": 0x0020,
            "rectangle": (10, 44, 140, 68),
            "visible": True,
        },
    ])

    assert selected.safe_metadata() == {
        "control_id": 7004,
        "style": 0x0020,
        "rectangle": [10, 44, 140, 68],
        "visible": True,
        "password_hint": False,
    }


def test_select_password_edit_maps_stale_handle_without_leaking_exception_text():
    secret = "Handle 5001 is not a vaild window handle"
    with pytest.raises(AutoIpoError) as exc:
        select_password_edit([
            {"control": StalePasswordControl(), "style": 0x0020, "visible": True},
        ])

    assert exc.value.code == "THS_PASSWORD_CONTROL_HANDLE_STALE"
    assert secret not in str(exc.value)
    assert secret not in json.dumps(exc.value.as_dict(), ensure_ascii=False)


def test_password_control_state_stale_handle_is_structured():
    ui = ControlAwareFakeUI(
        [edit(1002, style=0x0020, top=44)],
        filled=False,
        current="旧账户",
        options=["甲"],
    )

    def stale(_control):
        raise RuntimeError("Handle 5005 is not a vaild window handle")

    ui.password_control_filled = stale
    with pytest.raises(AutoIpoError) as exc:
        switch_ths_account(account("甲"), "ths1", lambda: "secret", ui, 4)

    assert exc.value.code == "THS_PASSWORD_CONTROL_HANDLE_STALE"


def test_switch_ui_stale_handle_is_structured():
    ui = FakeUI(current="旧账户", options=["甲"], password_text="saved")

    def stale():
        raise RuntimeError("Handle 5006 is not a valid window handle")

    ui.current_account_name = stale
    with pytest.raises(AutoIpoError) as exc:
        switch_ths_account(account("甲"), "ths1", lambda: "secret", ui, 4)

    assert exc.value.code == "THS_UI_HANDLE_STALE"
    assert exc.value.context["stage"] == "current_account_name"
    assert "current_account_name" in exc.value.message


def test_switch_ui_stale_handle_reports_select_account_stage():
    ui = FakeUI(current="旧账户", options=["甲"], password_text="saved")

    def stale(_username):
        raise RuntimeError("Handle 5007 is not a valid window handle")

    ui.select_account = stale
    with pytest.raises(AutoIpoError) as exc:
        switch_ths_account(account("甲"), "ths1", lambda: "secret", ui, 4)

    assert exc.value.code == "THS_UI_HANDLE_STALE"
    assert exc.value.context["stage"] == "select_account"


def test_control_api_filled_password_only_clicks_login():
    ui = ControlAwareFakeUI(
        [edit(1001), edit(1002, style=0x0020, top=44)],
        filled=True,
        current="旧账户",
        options=["甲"],
    )
    reads = []

    result = switch_ths_account(
        account("甲"),
        client="ths1",
        password_reader=lambda: reads.append(1),
        ui=ui,
        timeout_s=4,
    )

    assert result.status == "switched"
    assert reads == []
    assert ui.password_control_writes == []
    assert ("password_control_filled", 1002) in ui.events
    assert "click_login" in ui.events


def test_control_api_empty_password_uses_credential_fill_path_once():
    ui = ControlAwareFakeUI(
        [edit(1001), edit(1002, style=0x0020, top=44)],
        filled=False,
        current="旧账户",
        options=["甲"],
    )
    reads = []

    def reader():
        reads.append(1)
        return "mock-credential-value"

    result = switch_ths_account(account("甲"), "ths1", reader, ui, 4)

    assert result.status == "switched"
    assert reads == [1]
    assert len(ui.password_control_writes) == 1
    selected, password = ui.password_control_writes[0]
    assert selected.control_id == 1002
    assert password == "mock-credential-value"


def test_switch_reuses_current_account_without_password_or_gui_close():
    ui = FakeUI(current="甲")
    password_reads = []

    result = switch_ths_account(
        account("甲"), client="ths1", password_reader=lambda: password_reads.append(1),
        ui=ui, timeout_s=4,
    )
    assert result.status == "reused"
    assert result.username == "甲"
    assert password_reads == []
    assert ui.events[0][0] == "wait_for_main_window"
    assert ui.events[-1] == "current_account_name"


def test_switch_with_filled_password_clicks_login_without_reader():
    ui = FakeUI(current="旧账户", options=["甲"], password_text="saved")
    password_reads = []

    result = switch_ths_account(
        account("甲"), client="ths1", password_reader=lambda: password_reads.append(1),
        ui=ui, timeout_s=4,
    )
    assert result.status == "switched"
    assert result.username == "甲"
    assert password_reads == []
    assert ui.set_password_calls == []
    assert "click_login" in ui.events


def test_switch_with_empty_password_reads_once_fills_then_logs_in():
    ui = FakeUI(current="旧账户", options=["甲"], password_text="")
    reads = []

    def reader():
        reads.append(1)
        return "secret-value"

    result = switch_ths_account(account("甲"), "ths1", reader, ui, 4)
    assert result.status == "switched"
    assert reads == [1]
    assert ui.set_password_calls == ["secret-value"]


def test_ambiguous_display_name_stops_and_saves_screenshot():
    ui = FakeUI(current="旧账户", options=["同名", "同名"], password_text="saved")
    with pytest.raises(AutoIpoError) as exc:
        switch_ths_account(account("同名"), "ths1", lambda: "x", ui, 4)
    assert exc.value.code == "THS_ACCOUNT_AMBIGUOUS"
    assert ui.shots
    assert "click_login" not in ui.events


def test_missing_target_stops_and_saves_screenshot():
    ui = FakeUI(current="旧账户", options=["其他"], password_text="saved")
    with pytest.raises(AutoIpoError) as exc:
        switch_ths_account(account("目标"), "ths1", lambda: "x", ui, 4)
    assert exc.value.code == "THS_ACCOUNT_NOT_FOUND"
    assert ui.shots


def test_switch_popup_timeout_is_structured_and_screenshots():
    ui = FakeUI(current="旧账户", options=["甲"], password_text="saved", popup=False)
    with pytest.raises(AutoIpoError) as exc:
        switch_ths_account(account("甲"), "ths1", lambda: "x", ui, 3)
    assert exc.value.code == "THS_SWITCH_TIMEOUT"
    assert ui.shots


def test_login_window_timeout_is_structured_and_screenshots():
    ui = FakeUI(current="旧账户", options=["甲"], password_text="saved", login_window=False)
    with pytest.raises(AutoIpoError) as exc:
        switch_ths_account(account("甲"), "ths1", lambda: "x", ui, 3)
    assert exc.value.code == "THS_LOGIN_WINDOW_TIMEOUT"
    assert ui.shots


def test_login_main_window_timeout_is_structured_and_screenshots():
    ui = FakeUI(current="旧账户", options=["甲"], password_text="saved", main_window=False)
    with pytest.raises(AutoIpoError) as exc:
        switch_ths_account(account("甲"), "ths1", lambda: "x", ui, 3)
    assert exc.value.code == "THS_MAIN_WINDOW_TIMEOUT"
    assert ui.shots


def test_password_reader_failure_never_leaks_exception_text():
    secret = "plain-password-must-not-leak"
    ui = FakeUI(current="旧账户", options=["甲"], password_text="")

    def reader():
        raise RuntimeError(secret)

    with pytest.raises(AutoIpoError) as exc:
        switch_ths_account(account("甲"), "ths1", reader, ui, 4)
    assert exc.value.code == "THS_PASSWORD_READ_FAILED"
    assert secret not in str(exc.value)
    assert secret not in json.dumps(exc.value.as_dict(), ensure_ascii=False)
    assert ui.shots


def test_password_reader_preserves_structured_error_code():
    ui = FakeUI(current="旧账户", options=["甲"], password_text="")

    def reader():
        raise AutoIpoError("THS_PASSWORD_MISSING", "缺少密码", "补录密码")

    with pytest.raises(AutoIpoError) as exc:
        switch_ths_account(account("甲"), "ths1", reader, ui, 4)

    assert exc.value.code == "THS_PASSWORD_MISSING"


def test_empty_password_reader_result_is_structured_failure():
    ui = FakeUI(current="旧账户", options=["甲"], password_text="")
    with pytest.raises(AutoIpoError) as exc:
        switch_ths_account(account("甲"), "ths1", lambda: "", ui, 4)
    assert exc.value.code == "THS_PASSWORD_READ_FAILED"
    assert ui.shots


def test_close_uses_popup_exit_button_waits_and_verifies_exit():
    ui = FakeUI(current="甲")
    close_ths_client(ui, timeout_s=4)
    assert "close_main_window" in ui.events
    assert ("wait_for_popup", "退出") in ui.events
    assert ("click_popup", "退出") in ui.events
    assert "wait_for_client_exit" in ui.events
    assert not any("kill" in str(event).lower() for event in ui.events)


def test_close_failure_is_structured_and_screenshots():
    ui = FakeUI(current="甲", click_popup=False)
    with pytest.raises(AutoIpoError) as exc:
        close_ths_client(ui, timeout_s=4)
    assert exc.value.code == "THS_CLIENT_EXIT_FAILED"
    assert ui.shots


def test_close_exit_popup_timeout_is_structured_and_screenshots():
    ui = FakeUI(current="甲", popup=False)
    with pytest.raises(AutoIpoError) as exc:
        close_ths_client(ui, timeout_s=1)
    assert exc.value.code == "THS_CLIENT_EXIT_POPUP_TIMEOUT"
    assert ui.shots


def test_close_exit_unconfirmed_is_structured_and_never_force_kills():
    ui = FakeUI(current="甲", client_exited=False)
    with pytest.raises(AutoIpoError) as exc:
        close_ths_client(ui, timeout_s=1)
    assert exc.value.code == "THS_CLIENT_EXIT_TIMEOUT"
    assert ui.shots
    assert not any("kill" in str(event).lower() for event in ui.events)
