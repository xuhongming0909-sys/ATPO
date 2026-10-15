# AI-SUMMARY: Server酱微信推送封装（SendKey 从 config/secrets.yaml 读取，永不打印）
import requests

from shared.config import load_secrets

API = "https://sctapi.ftqq.com/{sendkey}.send"
TIMEOUT = 20


def send(title: str, desp: str) -> dict:
    sendkey = load_secrets().get("serverchan", {}).get("sendkey")
    if not sendkey:
        raise RuntimeError("config/secrets.yaml 缺少 serverchan.sendkey")
    resp = requests.post(
        API.format(sendkey=sendkey),
        data={"title": title, "desp": desp},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    result = resp.json()
    if result.get("code") != 0:
        raise RuntimeError(f"Server酱推送失败: {result.get('message')}")
    return result
