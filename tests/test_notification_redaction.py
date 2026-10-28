# AI-SUMMARY: Server酱与统一错误脱敏测试——凭据（密码/验证码/SendKey/token/URL）永不输出；账户识别信息完整保留
import pytest

from shared.errors import AutoIpoError, sanitize_sensitive_text, sanitize_sensitive_value


def test_request_exception_does_not_leak_sendkey_or_url(monkeypatch):
    import requests
    from notification import serverchan
    monkeypatch.setattr(serverchan, "load_secrets", lambda: {"serverchan": {"sendkey": "SCTSECRET123"}})

    def fail(*_args, **_kwargs):
        raise requests.RequestException("POST https://sctapi.ftqq.com/SCTSECRET123.send failed")

    monkeypatch.setattr(serverchan.requests, "post", fail)
    with pytest.raises(RuntimeError, match="Server酱网络请求失败") as excinfo:
        serverchan.send("标题", "正文")
    message = str(excinfo.value)
    assert "SCTSECRET123" not in message
    assert "https://" not in message
    assert "sctapi" not in message
    assert excinfo.value.__cause__ is None


def test_http_error_does_not_leak_sendkey(monkeypatch):
    from notification import serverchan

    class Response:
        status_code = 500
        def raise_for_status(self):
            raise RuntimeError("500 https://sctapi.ftqq.com/SCTSECRET123.send")
        def json(self):
            return {}

    monkeypatch.setattr(serverchan, "load_secrets", lambda: {"serverchan": {"sendkey": "SCTSECRET123"}})
    monkeypatch.setattr(serverchan.requests, "post", lambda *_a, **_k: Response())
    with pytest.raises(RuntimeError, match="Server酱 HTTP 500") as excinfo:
        serverchan.send("标题", "正文")
    assert "SCTSECRET123" not in str(excinfo.value)


def test_serverchan_api_error_is_sanitized(monkeypatch):
    from notification import serverchan

    class Response:
        status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            return {
                "code": 40001,
                "message": "bad key SCTSECRET123 account=326219248611 "
                           "password=top-secret captcha=9565 url=https://example.com/x",
            }

    monkeypatch.setattr(serverchan, "load_secrets", lambda: {"serverchan": {"sendkey": "SCTSECRET123"}})
    monkeypatch.setattr(serverchan.requests, "post", lambda *_a, **_k: Response())
    with pytest.raises(RuntimeError, match="Server酱推送失败") as excinfo:
        serverchan.send("标题", "正文")
    message = str(excinfo.value)
    for secret in ("SCTSECRET123", "top-secret", "9565", "https://", "example.com"):
        assert secret not in message
    assert "326219248611" in message  # 资金账号完整保留，便于定位账户


def test_missing_sendkey_error_has_no_key_material(monkeypatch):
    from notification import serverchan
    monkeypatch.setattr(serverchan, "load_secrets", lambda: {"serverchan": {"sendkey": ""}})
    with pytest.raises(RuntimeError, match="缺少 serverchan.sendkey"):
        serverchan.send("标题", "正文")


def test_shared_error_text_and_recursive_payload_are_redacted():
    exc = AutoIpoError(
        "SAFE_CODE",
        "fund_account=326219248611 password=超级密 码 captcha=9565 sendkey=SCTSECRET123",
        "查看 https://example.com/path?token=SCTSECRET123",
        {"nested": {"资金账号": "326219248611", "url": "https://example.com/a"}},
    )
    message = str(exc)
    payload = exc.as_dict()
    flat = f"{message}|{payload}"
    for secret in ("超级密 码", "9565", "SCTSECRET123", "https://", "example.com"):
        assert secret not in flat
    assert "326219248611" in flat  # 资金账号完整保留


def test_long_account_is_fully_preserved():
    assert sanitize_sensitive_text("账号 326219248611") == "账号 326219248611"
    assert sanitize_sensitive_value({"account": "326219248611"}) == {"account": "326219248611"}

def test_bare_url_and_nested_format_error_are_removed():
    assert "sctapi" not in sanitize_sensitive_text("POST sctapi.ftqq.com/SCTSECRET123.send")
    exc = AutoIpoError(
        "SAFE_CODE",
        "失败",
        "",
        {"nested": {"password": "top-secret", "资金账号": "326219248611"}},
    )
    from shared.errors import format_error
    text = format_error(exc)
    assert "top-secret" not in text
    assert "326219248611" in text  # 资金账号完整保留


# RED: 普通操作信息不脱敏：完整 THS 用户名、账户显示名、状态和错误要能定位问题。
def test_operational_usernames_names_and_status_are_not_masked():
    text = sanitize_sensitive_text("mx_525378109 平安证券-张*龙 status=wrong_account detail=切换失败")
    assert "mx_525378109" in text
    assert "平安证券-张*龙" in text
    assert "wrong_account" in text
    assert "切换失败" in text


def test_receipt_keeps_ths_username_and_full_display_name():
    from notification.receipts import render_receipt

    title, body = render_receipt("login", {
        "date": "2026-10-18",
        "clients": [{
            "id": "ths1",
            "accounts": [{
                "account": "mx_525378109",
                "ths_account": "mx_525378109",
                "display_name": "平安证券-张*龙",
                "login_status": "wrong_account",
                "detail": "当前账户不一致",
            }],
        }],
    })
    assert "成功 0" in title
    assert "mx_525378109" in body
    assert "平安证券-张*龙" in body
    assert "wrong_account" in body


# RED: 普通资金账号属于本人账户识别信息，可以显示；凭据仍必须隐藏。
def test_fund_account_is_visible_but_credentials_remain_hidden():
    from shared.errors import sanitize_sensitive_value
    from notification.receipts import render_receipt

    value = sanitize_sensitive_value({
        "fund_account": "326219242115",
        "password": "top-secret",
        "captcha": "9565",
        "sendkey": "SCTSECRET123",
    })
    assert value["fund_account"] == "326219242115"
    assert value["password"] == "***"
    assert value["captcha"] == "***"
    assert value["sendkey"] == "***"
    _, body = render_receipt("login", {
        "date": "2026-10-18",
        "clients": [{"id": "mx_test", "accounts": [{
            "account_key": "fund-1",
            "display_name": "平安证券-张*龙",
            "ths_account": "mx_test",
            "fund_account": "326219242115",
            "fund_account_tail4": "2115",
            "login_status": "ready",
        }]}],
    })
    assert "326219242115" in body
    assert "top-secret" not in body
    assert "SCTSECRET123" not in body
def test_serverchan_error_includes_api_message(monkeypatch):
    """HTTP 400 等错误透传服务端 message（已脱敏），便于区分额度/内容问题。"""

    class Resp:
        status_code = 400
        text = "{}"

        def json(self):
            return {"code": 40001, "message": "[AUTH]超过当天的发送次数限制[5]，请稍后再试"}

    monkeypatch.setattr("notification.serverchan.requests.post", lambda *a, **k: Resp())
    monkeypatch.setattr(
        "notification.serverchan.load_secrets",
        lambda: {"serverchan": {"sendkey": "TESTKEY123"}},
    )
    import pytest

    from notification.serverchan import send

    with pytest.raises(RuntimeError) as excinfo:
        send("t", "d")
    message = str(excinfo.value)
    assert "HTTP 400" in message
    assert "发送次数限制" in message
    assert "TESTKEY123" not in message  # sendkey 不得泄漏
