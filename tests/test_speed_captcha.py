# AI-SUMMARY: 速度与验证码测试——当日委托 OCR 禁复制、批量核验走 OCR、数字验证码识别
import types

import execution.ipo_page as ipo
import execution.ths_client as tc
from execution.captcha_login import _locate_captcha


class _User:
    def __init__(self):
        self.submit_calls = 0

    def _handle_pop_dialogs(self):
        self.submit_calls += 1
        return {"message": "success"}

    @property
    def today_entrusts(self):
        raise AssertionError("不得读取 jqktrader.today_entrusts/剪贴板")


def test_read_today_entrusts_uses_screen_ocr(monkeypatch):
    calls = {}

    class User:
        _main = None

        def _switch_left_menus(self, path):
            calls["menu"] = path

    monkeypatch.setattr(tc, "read_grid_via_ocr",
                        lambda user, control_id, header_keys=None: calls.update(
                            control_id=control_id, header_keys=header_keys
                        ) or [{"证券代码": "070887", "委托数量": "10000"}])
    rows = tc.read_today_entrusts_via_ocr(User())
    assert rows == [{"证券代码": "070887", "委托数量": "10000"}]
    assert calls["menu"] == ["查询[F4]", "当日委托"]
    assert "证券代码" in calls["header_keys"]


def test_batch_subscribe_verifies_with_screen_ocr(monkeypatch, tmp_path):
    from execution.order_ledger import OrderLedger

    monkeypatch.setattr(ipo, "read_ipo_grid", lambda _user: [
        {"新股名称": "中鼎转03", "新股代码": "070887", "申购数量": "10000"}
    ])
    monkeypatch.setattr(ipo, "_click_button", lambda *_a, **_k: None)
    monkeypatch.setattr(ipo, "_click_grid_row", lambda *_a, **_k: None)
    monkeypatch.setattr("execution.ths_client.read_today_entrusts_via_ocr",
                        lambda _user: [{"证券代码": "070887", "委托数量": "10000", "委托状态": "已报"}])
    user = _User()
    rows = ipo.batch_subscribe(
        user,
        ledger=OrderLedger("2026-10-22", root=tmp_path),
        account_id="a",
        allowlist=[{"name": "中鼎转03", "apply_code": "070887"}],
    )
    assert rows[0]["status"] == "submitted"
    assert rows[0]["verified"] is True
    assert user.submit_calls == 1


def test_numeric_captcha_accepts_five_digits():
    dialog = types.SimpleNamespace()

    def items(_dialog):
        return [
            {"text": "35761", "left": 240, "top": 40, "right": 310, "bottom": 70},
        ], (0, 0, 400, 100)

    class Edit:
        def rectangle(self):
            return types.SimpleNamespace(left=80, right=180, top=38, bottom=72)

    dialog.descendants = lambda class_name=None: [Edit()] if class_name == "Edit" else []
    import execution.captcha_login as captcha
    monkeypatch_items = items
    original = captcha._ocr_dialog_items
    captcha._ocr_dialog_items = monkeypatch_items
    try:
        located = _locate_captcha(dialog)
    finally:
        captcha._ocr_dialog_items = original
    assert located is not None
    assert located[1] == "35761"


def test_numeric_captcha_prompt_clicks_confirm(monkeypatch):
    import execution.captcha_login as captcha

    state = {"dialog": None}

    class Edit:
        def __init__(self):
            self.value = None

        def set_edit_text(self, value):
            self.value = value

        def rectangle(self):
            return types.SimpleNamespace(left=80, right=180, top=38, bottom=72)

    class Button:
        def __init__(self):
            self.clicked = 0

        def window_text(self):
            return "确定"

        def click_input(self):
            self.clicked += 1
            state["dialog"] = None

    edit = Edit()
    button = Button()
    dialog = types.SimpleNamespace(descendants=lambda class_name=None: {
        "Edit": [edit], "Button": [button]
    }.get(class_name, []))
    state["dialog"] = dialog
    monkeypatch.setattr(captcha, "_find_dialog_window", lambda pids, texts: state["dialog"])
    monkeypatch.setattr(captcha, "_locate_captcha", lambda _dialog: (edit, "9565"))
    monkeypatch.setattr(captcha.time, "sleep", lambda _s: None)

    assert captcha.try_captcha_prompt({1}) is True
    assert edit.value == "9565"
    assert button.clicked == 1
def test_password_login_fills_password_checkbox_captcha_and_clicks(monkeypatch):
    """DPAPI 密码自动填充：密码框 set_edit_text、勾保存密码、填验证码、点登录。"""
    import execution.captcha_login as cl

    filled = {}

    class Edit:
        def __init__(self, text, top):
            self._text = text
            self._top = top

        def window_text(self):
            return self._text

        def rectangle(self):
            return type("R", (), {"top": self._top, "bottom": self._top + 20})()

        def set_edit_text(self, value):
            filled[id(self)] = value
            self._text = value

    account_edit = Edit("326219248611", 100)
    password_edit = Edit("", 140)
    captcha_edit = Edit("", 180)

    clicked = []

    class Checkbox:
        def window_text(self):
            return "保存密码"

        def get_toggle_state(self):
            return 0

        def click_input(self):
            clicked.append("checkbox")

    class LoginBtn:
        def window_text(self):
            return "登录"

        def click_input(self):
            clicked.append("login")

    class Dialog:
        def descendants(self, class_name=""):
            if class_name == "Edit":
                return [account_edit, password_edit, captcha_edit]
            if class_name == "Button":
                return [Checkbox(), LoginBtn()]
            return []

    monkeypatch.setattr(cl, "_locate_captcha", lambda d: (captcha_edit, "9565"))
    monkeypatch.setattr(cl.time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def gone_after_click(pids):
        calls["n"] += 1
        return None if calls["n"] >= 2 else Dialog()

    monkeypatch.setattr(cl, "_find_login_dialog", gone_after_click)

    assert cl.try_password_login({1}, "secret-pw") is True
    assert password_edit._text == "secret-pw"   # Edit.set_edit_text 已回写实例
    assert captcha_edit._text == "9565"
    assert clicked == ["checkbox", "login"]


def test_password_login_refuses_empty_password():
    import execution.captcha_login as cl

    assert cl.try_password_login({1}, "") is False


def test_password_for_fund_account_matches_and_decrypts(monkeypatch):
    import execution.captcha_login as cl

    monkeypatch.setattr(
        cl, "load_secrets",
        lambda: {"accounts_secrets": {"揭*": {"fund_account": "123456789", "password_enc": "ENC"}}},
    ) if hasattr(cl, "load_secrets") else None
    # load_secrets 是函数内导入：patch shared.config.load_secrets
    import shared.config as config_mod

    monkeypatch.setattr(
        config_mod, "load_secrets",
        lambda: {"accounts_secrets": {"揭*": {"fund_account": "123456789", "password_enc": "ENC"}}},
    )
    import shared.credstore as credstore

    monkeypatch.setattr(credstore, "decrypt_text", lambda token: "plain-pw" if token == "ENC" else "")
    assert cl.password_for_fund_account("123456789") == "plain-pw"
    assert cl.password_for_fund_account("999888777") == ""
    assert cl.password_for_fund_account("12") == ""
