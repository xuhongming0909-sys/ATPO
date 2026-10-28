# AI-SUMMARY: 凭据加密存储测试——DPAPI 往返、密文不等于明文
from shared.credstore import decrypt_text, encrypt_text


def test_dpapi_roundtrip():
    token = encrypt_text("my-secret-password-123")
    assert "my-secret-password-123" not in token   # 密文不含明文
    assert decrypt_text(token) == "my-secret-password-123"


def test_empty_password_roundtrip():
    assert decrypt_text(encrypt_text("")) == ""
