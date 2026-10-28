# AI-SUMMARY: 凭据加密存储——Windows DPAPI（绑定本机当前用户），密文存 config/secrets.yaml，明文不落盘不进 git
import base64

import win32crypt

def encrypt_text(plain: str) -> str:
    blob = win32crypt.CryptProtectData(plain.encode("utf-8"), None, None, None, None, 0)
    return base64.b64encode(blob).decode("ascii")


def decrypt_text(token: str) -> str:
    blob = base64.b64decode(token.encode("ascii"))
    return win32crypt.CryptUnprotectData(blob, None, None, None, 0)[1].decode("utf-8")
