# AI-SUMMARY: 沪深交易日判定——东财上证指数日K线权威数据 + 本机文件缓存 + 周末快速否决；网络失败返回 None 由调用方放行
from __future__ import annotations

import json
from datetime import date

import requests

from shared.paths import ensure_runtime_dirs, runtime_path

# 上证指数（1.000001）日K线：有K线即为交易日，数据源与打新日历一致（东方财富）
_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"


def _cache_path():
    ensure_runtime_dirs()
    return runtime_path("trading_days.json")


def _load_cache() -> dict[str, bool]:
    try:
        data = json.loads(_cache_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_cache(cache: dict[str, bool]) -> None:
    try:
        _cache_path().write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8", newline="\n")
    except Exception:
        pass


def _fetch_month_kline_days(day: date) -> set[str]:
    """取当月截至目标日的全部K线日期（一次请求覆盖缓存未命中场景）。"""
    beg = day.replace(day=1).strftime("%Y%m%d")
    end = day.strftime("%Y%m%d")
    resp = requests.get(
        _KLINE_URL,
        params={
            "secid": "1.000001",
            "klt": 101,
            "fqt": 0,
            "beg": beg,
            "end": end,
            "fields1": "f1",
            "fields2": "f51",
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json().get("data") or {}
    return {str(row).split(",")[0] for row in (data.get("klines") or [])}


def is_trading_day(day: str) -> bool | None:
    """True=交易日；False=非交易日；None=无法确认（网络失败，调用方按工作日放行并自行留痕）。

    周末必为非交易日直接返回；工作日查东财日K线；结果按日缓存到 runtime_data/trading_days.json。
    """
    target = date.fromisoformat(day)
    if target.weekday() >= 5:
        return False
    if target >= date.today():
        # 当日/未来日盘前无 K 线，东财缺失会误判非交易日并毒化缓存；工作日直接放行
        return True
    cache = _load_cache()
    if day in cache:
        return bool(cache[day])
    try:
        days = _fetch_month_kline_days(target)
    except Exception:
        return None
    result = day in days
    cache[day] = result
    _save_cache(cache)
    return result
