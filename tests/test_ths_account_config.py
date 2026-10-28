# AI-SUMMARY: 单客户端多同花顺登录账户配置测试——显示名唯一、10 户上限和 DPAPI 密码读取
import pytest

from execution.ths_account_config import load_ths_account_mode, read_ths_password
from shared.errors import AutoIpoError


def _cfg():
    return {
        "execution": {
            "ths_account_switch": {
                "hexin_path": "C:/ths/hexin.exe",
                "xiadan_path": "C:/ths/xiadan.exe",
                "max_ths_accounts": 10,
                "max_fund_accounts_per_ths": 10,
                "accounts": [
                    {"username": "mx_one", "enabled": True},
                    {"username": "mx_two", "enabled": False},
                ],
            }
        }
    }


def test_loads_display_names_without_custom_ids():
    mode = load_ths_account_mode(_cfg())
    assert [a.username for a in mode.accounts] == ["mx_one", "mx_two"]
    assert [a.enabled for a in mode.accounts] == [True, False]
    assert mode.max_ths_accounts == 10
    assert mode.max_fund_accounts_per_ths == 10


def test_rejects_duplicate_display_name():
    cfg = _cfg()
    cfg["execution"]["ths_account_switch"]["accounts"][1]["username"] = "mx_one"
    with pytest.raises(AutoIpoError) as exc:
        load_ths_account_mode(cfg)
    assert exc.value.code == "THS_ACCOUNT_DUPLICATE"


def test_rejects_more_than_ten_ths_accounts():
    cfg = _cfg()
    cfg["execution"]["ths_account_switch"]["accounts"] = [
        {"username": f"mx_{i}", "enabled": True} for i in range(11)
    ]
    with pytest.raises(AutoIpoError) as exc:
        load_ths_account_mode(cfg)
    assert exc.value.code == "THS_ACCOUNT_LIMIT"


@pytest.mark.parametrize("key", ["max_ths_accounts", "max_fund_accounts_per_ths"])
@pytest.mark.parametrize("value", [-1, 0, 11, 1.0, "10", True])
def test_rejects_invalid_account_limits(key, value):
    cfg = _cfg()
    cfg["execution"]["ths_account_switch"][key] = value
    with pytest.raises(AutoIpoError) as exc:
        load_ths_account_mode(cfg)
    assert exc.value.code == "THS_ACCOUNT_LIMIT_INVALID"


def test_reads_password_from_dpapi_secret(monkeypatch):
    monkeypatch.setattr(
        "execution.ths_account_config.load_secrets",
        lambda: {"ths_account_secrets": {"mx_one": {"password_enc": "token"}}},
    )
    monkeypatch.setattr("execution.ths_account_config.decrypt_text", lambda token: f"secret-{token}")
    assert read_ths_password("mx_one") == "secret-token"


def test_decrypt_failure_does_not_leak_secret(monkeypatch):
    monkeypatch.setattr(
        "execution.ths_account_config.load_secrets",
        lambda: {"ths_account_secrets": {"mx_one": {"password_enc": "token"}}},
    )
    monkeypatch.setattr(
        "execution.ths_account_config.decrypt_text",
        lambda _token: (_ for _ in ()).throw(RuntimeError("plaintext-password")),
    )
    with pytest.raises(AutoIpoError) as exc:
        read_ths_password("mx_one")
    assert exc.value.code == "THS_PASSWORD_DECRYPT_FAILED"
    assert "plaintext-password" not in str(exc.value.context)
    assert "plaintext-password" not in str(exc.value)


def test_missing_password_is_structured_error(monkeypatch):
    monkeypatch.setattr("execution.ths_account_config.load_secrets", lambda: {})
    with pytest.raises(AutoIpoError) as exc:
        read_ths_password("mx_one")
    assert exc.value.code == "THS_PASSWORD_MISSING"
    assert "mx_one" in exc.value.message
