# AI-SUMMARY: 一键打新弹窗清理测试——勾选「不再自动弹出」后关窗，绝不点申购类按钮
import execution.login as login


class _FakeCheckbox:
    def __init__(self, checked):
        self._checked = checked
        self.clicks = 0

    def window_text(self):
        return "30天内不再自动弹出"

    def get_toggle_state(self):
        return 1 if self._checked else 0

    def click_input(self):
        self.clicks += 1
        self._checked = True


class _FakeYijiandaxinWindow:
    def __init__(self, checkbox=None):
        self._checkbox = checkbox
        self.closed = 0
        self.title = "一键打新"

    def process_id(self):
        return 123

    def is_visible(self):
        return True

    def class_name(self):
        return "#32770"

    def window_text(self):
        return self.title

    def descendants(self, class_name=""):
        if class_name == "Button":
            return [self._checkbox] if self._checkbox else []
        return []

    def close(self):
        self.closed += 1


def _patch_desktop(monkeypatch, windows):
    class _Desktop:
        @staticmethod
        def windows():
            return windows

    monkeypatch.setattr(login, "Desktop", lambda backend="win32": _Desktop())
    monkeypatch.setattr(login, "_xiadan_pids", lambda client=None: {123})
    monkeypatch.setattr(login.time, "sleep", lambda _s: None)


def test_dismiss_popups_checks_never_show_then_closes(monkeypatch):
    checkbox = _FakeCheckbox(checked=False)
    window = _FakeYijiandaxinWindow(checkbox)
    _patch_desktop(monkeypatch, [window])
    login._dismiss_popups()
    assert checkbox.clicks == 1
    assert window.closed == 1


def test_dismiss_popups_skips_login_dialog(monkeypatch):
    window = _FakeYijiandaxinWindow(_FakeCheckbox(checked=False))
    window.title = "委托下单"
    _patch_desktop(monkeypatch, [window])
    login._dismiss_popups()
    assert window.closed == 0


def test_close_modal_dialogs_marks_never_show_before_close(monkeypatch):
    checkbox = _FakeCheckbox(checked=False)
    window = _FakeYijiandaxinWindow(checkbox)
    _patch_desktop(monkeypatch, [window])
    assert login.close_modal_dialogs() == 1
    assert checkbox.clicks == 1
    assert window.closed == 1


def test_close_modal_dialogs_keeps_main_trading_window(monkeypatch):
    window = _FakeYijiandaxinWindow(_FakeCheckbox(checked=False))
    window.title = "网上股票交易系统 6.0"
    _patch_desktop(monkeypatch, [window])
    assert login.close_modal_dialogs() == 0
    assert window.closed == 0
