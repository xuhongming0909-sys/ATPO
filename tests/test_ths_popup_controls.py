# AI-SUMMARY: 同花顺关闭/切换弹窗测试——无文本自绘按钮按集中 control_id 精确定位
from execution.ths_account_ui import HexinSwitchUI


class Button:
    def __init__(self, control_id, on_click, *, input_only=False):
        self._control_id = control_id
        self._on_click = on_click
        self._input_only = input_only

    def control_id(self):
        return self._control_id

    def window_text(self):
        return ""

    def click(self):
        if self._input_only:
            raise AssertionError("physical click_input should be preferred")
        self._on_click(self._control_id)

    def click_input(self):
        self._on_click(self._control_id)


class Window:
    def __init__(self, buttons):
        self._buttons = buttons

    def window_text(self):
        return "同花顺"

    def class_name(self):
        return "#32770"

    def descendants(self, class_name=None):
        return list(self._buttons) if class_name == "Button" else []


def test_popup_control_id_selects_exit_when_button_text_is_empty():
    clicked = []
    buttons = [Button(value, clicked.append) for value in (20199, 20149, 21042)]
    ui = HexinSwitchUI(
        client=object(),
        cfg={"gui": {"ths_account_switch": {
            "switch_account_control_id": 20199,
            "cancel_control_id": 20149,
            "exit_control_id": 21042,
        }}},
    )
    ui._windows = lambda visible_only=True: [Window(buttons)]
    assert ui.wait_for_popup(0, "退出") is True
    assert ui.click_popup("退出") is True
    assert clicked == [21042]




def test_popup_prefers_physical_click_input_for_custom_buttons():
    clicked = []
    buttons = [
        Button(20199, clicked.append, input_only=True),
        Button(20149, clicked.append, input_only=True),
        Button(21042, clicked.append, input_only=True),
    ]
    ui = HexinSwitchUI(
        client=object(),
        cfg={"gui": {"ths_account_switch": {
            "switch_account_control_id": 20199,
            "cancel_control_id": 20149,
            "exit_control_id": 21042,
        }}},
    )
    ui._windows = lambda visible_only=True: [Window(buttons)]

    assert ui.click_popup("切换账号") is True
    assert clicked == [20199]




def test_saved_password_checkbox_supplements_cross_process_length(monkeypatch):
    import sys
    import types

    class Checkbox:
        def window_text(self):
            return "保存密码"

        def get_toggle_state(self):
            return 1

    class LoginWindow:
        def descendants(self, class_name=""):
            return [Checkbox()] if class_name == "Button" else []

    class Edit:
        handle = 123

    fake_gui = types.ModuleType("win32gui")
    fake_gui.GetWindowTextLength = lambda _handle: 0
    monkeypatch.setitem(sys.modules, "win32gui", fake_gui)
    ui = HexinSwitchUI(
        client=object(),
        cfg={"gui": {"ths_account_switch": {
            "saved_password_checkbox_text": "保存密码",
        }}},
    )
    ui._login_window = lambda: LoginWindow()
    ui._password_edit = lambda _control: Edit()

    assert ui.password_control_filled(object()) is True





def test_login_button_prefers_physical_click(monkeypatch):
    events = []

    class Button:
        def window_text(self):
            return "登录"

        def control_id(self):
            return 1

        def click_input(self):
            events.append("click_input")

        def click(self):
            events.append("click")

    class Window:
        def descendants(self, class_name=""):
            return [Button()] if class_name == "Button" else []

    ui = HexinSwitchUI(client=object(), cfg={})
    monkeypatch.setattr(ui, "_login_window", lambda: Window())

    assert ui.click_login() is True
    assert events == ["click_input"]





def test_wait_for_main_window_retries_stale_enumeration(monkeypatch):
    ui = HexinSwitchUI(client=object(), cfg={}, sleep_fn=lambda _seconds: None)
    calls = []

    def main_window():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("Handle 123 is not a vaild window handle")
        return object()

    monkeypatch.setattr(ui, "_main_window", main_window)

    assert ui.wait_for_main_window(1) is True
    assert len(calls) == 2




def test_saved_password_checkbox_uses_bm_getcheck_fallback(monkeypatch):
    class Button:
        element_info = type("Info", (), {"handle": 77})()

        def window_text(self):
            return "保存密码"

        def get_toggle_state(self):
            return 0

    class Window:
        def descendants(self, class_name=""):
            return [Button()] if class_name == "Button" else []

    ui = HexinSwitchUI(client=object(), cfg={})
    monkeypatch.setattr(ui, "_login_window", lambda: Window())
    monkeypatch.setattr("win32gui.SendMessage", lambda handle, msg, wparam, lparam: 1)

    assert ui._saved_password_checkbox_checked() is True





def test_password_length_message_marks_saved_password_filled(monkeypatch):
    import sys
    import types

    class Edit:
        handle = 123

    fake_gui = types.ModuleType("win32gui")
    fake_gui.GetWindowTextLength = lambda _handle: 0
    fake_gui.SendMessage = lambda handle, msg, wparam, lparam: 12 if msg == 0x00C1 else 0
    monkeypatch.setitem(sys.modules, "win32gui", fake_gui)
    ui = HexinSwitchUI(client=object(), cfg={})
    ui._password_edit = lambda _control: Edit()

    assert ui.password_control_filled(object()) is True


def test_login_button_falls_back_to_screen_click_when_control_click_is_ignored():
    events = []

    class Button:
        def window_text(self):
            return "登录"

        def control_id(self):
            return 1

        def click_input(self):
            events.append("click_input")

        def click(self):
            events.append("click")

        def rectangle(self):
            return (10, 20, 30, 40)

    class Window:
        def descendants(self, class_name=""):
            return [Button()] if class_name == "Button" else []

    ui = HexinSwitchUI(client=object(), cfg={"gui": {"ths_account_switch": {
        "login_click_verify_wait_s": 0,
    }}})
    window = Window()
    ui._login_window = lambda: window
    ui._click_screen = lambda button: events.append("screen")

    assert ui.click_login() is True
    assert events == ["click_input", "screen"]



def test_screen_click_uses_non_absolute_mouse_events(monkeypatch):
    events = []

    class Button:
        def rectangle(self):
            return (10, 20, 30, 40)

    monkeypatch.setattr("win32api.SetCursorPos", lambda pos: events.append(("pos", pos)))
    monkeypatch.setattr(
        "win32api.mouse_event",
        lambda flags, x, y, data, extra=0: events.append(("event", flags, x, y)),
    )
    monkeypatch.setattr("win32con.MOUSEEVENTF_LEFTDOWN", 2)
    monkeypatch.setattr("win32con.MOUSEEVENTF_LEFTUP", 4)

    ui = HexinSwitchUI(client=object(), cfg={})
    assert ui._click_screen(Button()) is True
    assert events == [
        ("pos", (20, 30)),
        ("event", 2, 0, 0),
        ("event", 4, 0, 0),
    ]



def test_empty_title_main_window_is_accepted_by_size_and_pid_scope():
    class Rect:
        left = 0
        top = 0
        right = 1200
        bottom = 800

    class Window:
        handle = 123

        def window_text(self):
            return ""

        def class_name(self):
            return "#32768"

        def rectangle(self):
            return Rect()

    window = Window()
    ui = HexinSwitchUI(client=object(), cfg={})
    ui._windows = lambda visible_only=True: [window]
    assert ui._main_window() is window




def test_login_combo_uses_window_messages_without_mouse(monkeypatch):
    import sys
    import types

    sent = []

    class Combo:
        handle = 123

        def item_texts(self):
            return ["mx_one", "mx_two"]

        def select(self, _name):
            raise AssertionError("不得使用鼠标式 combo.select")

    class LoginWindow:
        def descendants(self, class_name=""):
            return [Combo()] if class_name == "ComboBox" else []

    fake_gui = types.ModuleType("win32gui")
    fake_gui.SendMessage = lambda handle, msg, wparam, lparam: sent.append((handle, msg, wparam, lparam))
    monkeypatch.setitem(sys.modules, "win32gui", fake_gui)

    ui = HexinSwitchUI(client=object(), cfg={}, known_ths_accounts=["mx_one", "mx_two"])
    ui._login_window = lambda: LoginWindow()
    assert ui.account_display_names() == ["mx_one", "mx_two"]
    ui.open_account_dropdown()
    ui.select_account("mx_two")
    assert sent == [(123, 0x014F, 1, 0), (123, 0x014E, 1, 0), (123, 0x014F, 0, 0)]
def test_default_username_ocr_uses_worker_result_without_oneshot(monkeypatch, tmp_path):
    """serve_request 成功时直接采用其结果，不得回退/引用未定义的一次性子进程变量。"""
    import execution.ths_account_windows as win_mod

    class Rect:
        left = 0
        top = 0
        right = 1200
        bottom = 800

    class Window:
        handle = 0

        def rectangle(self):
            return Rect()

    image = tmp_path / "u.png"
    image.write_bytes(b"x")

    class FakeImg:
        @staticmethod
        def save(path):
            with open(path, "wb") as fh:
                fh.write(b"x")

    monkeypatch.setattr("PIL.ImageGrab.grab", lambda bbox=None: FakeImg())
    monkeypatch.setattr(
        "shared.username_ocr.serve_request",
        lambda *a, **k: {"status": "matched", "username": "mx_one", "score": 0.99, "margin": 0.5},
    )

    calls = []

    def spy_oneshot(*a, **k):
        calls.append(a)
        class P:
            returncode = 0
            stdout = "{}"
        return P()

    monkeypatch.setattr("subprocess.run", spy_oneshot)
    monkeypatch.setattr(win_mod.time, "sleep", lambda _s: None)
    name = win_mod._default_username_ocr(
        Window(), ["mx_one", "mx_two"], {"username_ocr_x_ratio": 0.5, "username_ocr_top_px": 36}
    )
    assert name == "mx_one"
    assert not calls
