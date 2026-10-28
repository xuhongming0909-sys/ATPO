# AI-SUMMARY: Server酱微信推送封装（SendKey 从 config/secrets.yaml 读取，异常输出彻底脱敏）
import requests

from shared.config import load_secrets
from shared.errors import sanitize_sensitive_text

API = "https://sctapi.ftqq.com/{sendkey}.send"
TIMEOUT = 20


class _ServerchanError(RuntimeError):
    pass


def _safe_error(text: object, sendkey: str = "") -> str:
    message = sanitize_sensitive_text(text)
    return message.replace(sendkey, "***") if sendkey else message


def send(title: str, desp: str) -> dict:
    sendkey = load_secrets().get("serverchan", {}).get("sendkey")
    if not sendkey:
        raise RuntimeError("config/secrets.yaml 缺少 serverchan.sendkey")
    try:
        resp = requests.post(API.format(sendkey=sendkey), data={"title": title, "desp": desp}, timeout=TIMEOUT)
        status = int(getattr(resp, "status_code", 200))
        if not 200 <= status < 300:
            detail = ""
            try:
                payload = resp.json()
                if isinstance(payload, dict):
                    detail = str(payload.get("message") or payload.get("info") or "")
            except Exception:
                detail = (resp.text or "")[:120]
            suffix = f": {detail}" if detail else ""
            raise _ServerchanError(f"Server酱 HTTP {status}{suffix}")
        result = resp.json()
        if not isinstance(result, dict):
            raise _ServerchanError("Server酱响应格式错误")
        if result.get("code") != 0:
            detail = _safe_error(result.get("message") or "接口返回非零 code", sendkey)
            raise _ServerchanError(f"Server酱推送失败: {detail}")
        return result
    except _ServerchanError as exc:
        raise RuntimeError(_safe_error(str(exc), sendkey)) from None
    except requests.Timeout:
        raise RuntimeError("Server酱请求超时，请检查网络后重试") from None
    except requests.RequestException:
        raise RuntimeError("Server酱网络请求失败，请检查网络后重试") from None
    except Exception:
        raise RuntimeError("Server酱响应解析失败") from None