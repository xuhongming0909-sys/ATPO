# AI-SUMMARY: 从东方财富数据中心抓取打新日历（新股 RPTA_APP_IPOAPPLY / 可转债 RPT_BOND_CB_LIST）并规范化为统一结构
import requests

BASE = "https://datacenter-web.eastmoney.com/api/data/v1/get"
TIMEOUT = 20


def _query(report_name: str, date_field: str, day: str) -> list[dict]:
    params = {
        "sortColumns": date_field,
        "sortTypes": "-1",
        "pageSize": "50",
        "pageNumber": "1",
        "reportName": report_name,
        "columns": "ALL",
        "filter": f"({date_field}='{day}')",
    }
    resp = requests.get(BASE, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("success"):
        message = str(payload.get("message") or "")
        if payload.get("code") == 9201 or "数据为空" in message:
            return []
        raise RuntimeError(f"东方财富日历接口失败：{message or 'success=false'}")
    if not payload.get("result"):
        return []
    return payload["result"].get("data") or []


def _date10(value) -> str | None:
    return value[:10] if value else None


def parse_new_stock(raw: dict) -> dict:
    return {
        "kind": "新股",
        "code": raw["SECURITY_CODE"],
        "apply_code": raw.get("APPLY_CODE") or raw["SECURITY_CODE"],
        "name": raw["SECURITY_NAME_ABBR"],
        "market": raw.get("MARKET_TYPE_NEW") or raw.get("TRADE_MARKET"),
        "apply_date": _date10(raw.get("APPLY_DATE")),
        "apply_limit": raw.get("ONLINE_APPLY_UPPER"),
        "top_marketcap_wan": raw.get("TOP_APPLY_MARKETCAP"),
        "issue_price": raw.get("ISSUE_PRICE"),
        "ballot_pay_date": _date10(raw.get("BALLOT_PAY_DATE")),
    }


def parse_cb(raw: dict) -> dict:
    return {
        "kind": "可转债",
        "code": raw["SECURITY_CODE"],
        "apply_code": raw.get("CORRECODE") or raw["SECURITY_CODE"],
        "name": raw["SECURITY_NAME_ABBR"],
        "rating": raw.get("RATING"),
        "issue_scale_yi": raw.get("ACTUAL_ISSUE_SCALE"),
        "stock_name": raw.get("SECURITY_SHORT_NAME"),
        "apply_date": _date10(raw.get("PUBLIC_START_DATE")),
    }


def fetch_new_stocks(day: str) -> list[dict]:
    return [parse_new_stock(r) for r in _query("RPTA_APP_IPOAPPLY", "APPLY_DATE", day)]


def fetch_cbs(day: str) -> list[dict]:
    return [parse_cb(r) for r in _query("RPT_BOND_CB_LIST", "PUBLIC_START_DATE", day)]


_DAY_CACHE: dict = {}


def fetch_calendar_for(day: str, _fetchers: dict | None = None) -> dict:
    """day: YYYY-MM-DD。_fetchers 仅测试注入用。进程内按日缓存：一轮 15 户只抓一次。"""
    if _fetchers is not None:
        return {
            "day": day,
            "new_stocks": _fetchers["new_stocks"](day),
            "cbs": _fetchers["cbs"](day),
        }
    if day not in _DAY_CACHE:
        _DAY_CACHE[day] = {
            "day": day,
            "new_stocks": fetch_new_stocks(day),
            "cbs": fetch_cbs(day),
        }
    return _DAY_CACHE[day]
