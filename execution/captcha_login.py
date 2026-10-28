# AI-SUMMARY: 验证码登录弹窗自动填写——OCR 识别简单数字验证码，填充后点登录；失败回退关闭跳过
from __future__ import annotations

import re
import time
import uuid
from typing import Any

from shared.paths import runtime_path

_CAPTCHA_RE = re.compile(r"^\d{4,6}$")


def _find_dialog_window(pids: set[int], submit_texts: tuple[str, ...] = ("登录",)) -> Any | None:
    """在客户端进程内找含验证码输入的对话框。"""
    from pywinauto import Desktop

    wanted = tuple(str(value or "") for value in submit_texts if str(value or ""))
    for window in Desktop(backend="win32").windows():
        try:
            if window.process_id() not in pids or not window.is_visible():
                continue
            edits = list(window.descendants(class_name="Edit"))
            buttons = [str(b.window_text() or "") for b in window.descendants(class_name="Button")]
            if edits and any(any(text in button for text in wanted) for button in buttons):
                return window
        except Exception:
            continue
    return None

def _ocr_dialog_items(dialog: Any) -> tuple[list[dict], Any]:
    """截取对话框整体做 OCR，返回条目（屏幕绝对坐标）。"""
    from PIL import ImageGrab

    rect = dialog.rectangle()
    box = (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
    path = runtime_path("ocr", f"captcha_{uuid.uuid4().hex}.png")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        ImageGrab.grab(bbox=box).save(path)
        # 2026-10-27 排障：总是留一份最后抓取，验证码找不到时看这里
        try:
            import shutil
            shutil.copyfile(path, runtime_path("ocr", "debug_last_dialog.png"))
        except Exception:
            pass
        from shared.username_ocr import read_texts_with_ocr

        items = read_texts_with_ocr(path)
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
    for item in items:
        item["left"] = float(item.get("left", 0)) + box[0]
        item["top"] = float(item.get("top", 0)) + box[1]
        item["right"] = float(item.get("right", 0)) + box[0]
        item["bottom"] = float(item.get("bottom", 0)) + box[1]
    return items, box


def _digit_band_candidates(items: list[dict]) -> list[dict]:
    """把同一水平带上相邻的单字数字 OCR 条目合并为 4-6 位验证码候选。

    真实同花顺验证码常被 RapidOCR 切成单字条目（'2','0','5','8'），
    必须按水平带聚类、按 x 间隙拼接后才能成码。
    """
    digit_items = []
    for item in items:
        text = re.sub(r"\s+", "", str(item.get("text") or ""))
        if not text.isdigit() or not 1 <= len(text) <= 6:
            continue
        top = float(item.get("top", 0))
        bottom = float(item.get("bottom", 0))
        digit_items.append({
            "digits": text,
            "left": float(item.get("left", 0)),
            "right": float(item.get("right", 0)),
            "mid": (top + bottom) / 2,
        })
    bands: list[dict] = []
    for item in sorted(digit_items, key=lambda x: x["mid"]):
        for band in bands:
            if abs(band["mid"] - item["mid"]) <= 12:
                band["items"].append(item)
                band["mid"] = sum(x["mid"] for x in band["items"]) / len(band["items"])
                break
        else:
            bands.append({"mid": item["mid"], "items": [item]})
    candidates = []
    for band in bands:
        row = sorted(band["items"], key=lambda x: x["left"])
        run = ""
        run_left = 0.0
        run_mid = row[0]["mid"] if row else 0.0
        last_right = None
        for item in row:
            if last_right is not None and item["left"] - last_right > 60 and run:
                if 4 <= len(run) <= 6:
                    candidates.append({"digits": run, "left": run_left, "mid": run_mid})
                run = ""
            if not run:
                run_left = item["left"]
                run_mid = item["mid"]
            run += item["digits"]
            last_right = item["right"]
        if 4 <= len(run) <= 6:
            candidates.append({"digits": run, "left": run_left, "mid": run_mid})
    return candidates


def _retry_captcha_items(dialog: Any) -> list[dict]:
    """整窗 OCR 找不到验证码时：截取对话框右侧中部区域（验证码固定带）2x 放大重试。

    2026-10-27 实战：华宝浅灰小字验证码在整窗 OCR 中被漏检，裁剪放大后可读。
    """
    from PIL import Image, ImageGrab

    rect = dialog.rectangle()
    left, top = int(rect.left), int(rect.top)
    width = max(1, int(rect.right) - left)
    height = max(1, int(rect.bottom) - top)
    box = (
        left + int(width * 0.40), top + int(height * 0.25),
        left + width, top + int(height * 0.75),
    )
    image = ImageGrab.grab(bbox=box)
    image = image.resize((image.width * 2, image.height * 2), Image.LANCZOS)
    import uuid as _uuid
    from shared.paths import runtime_path
    path = runtime_path("ocr", f"captcha_retry_{_uuid.uuid4().hex}.png")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        image.save(path)
        items = read_texts_with_ocr(path)
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
    for item in items:
        item["left"] = float(item.get("left", 0)) / 2 + box[0]
        item["right"] = float(item.get("right", 0)) / 2 + box[0]
        item["top"] = float(item.get("top", 0)) / 2 + box[1]
        item["bottom"] = float(item.get("bottom", 0)) / 2 + box[1]
    return items


def _locate_captcha(dialog: Any) -> tuple[Any, str] | None:
    """OCR 找 4-6 位数字验证码（含单字拼接），验证码输入框 = 同一水平带上、位于其左侧的 Edit。"""
    items, _box = _ocr_dialog_items(dialog)
    if not _digit_band_candidates(items) and not [
        i for i in items
        if _CAPTCHA_RE.match(re.sub(r"\s+", "", str(i.get("text") or "")).strip())
    ]:
        items = _retry_captcha_items(dialog)
    digits = [
        item for item in items
        if _CAPTCHA_RE.match(re.sub(r"\s+", "", str(item.get("text") or "")).strip())
    ]
    code = ""
    digit_left = 0.0
    mid_y = 0.0
    if digits:
        digit = digits[0]
        code = re.sub(r"\s+", "", str(digit.get("text") or "")).strip()
        digit_left = float(digit.get("left", 0))
        mid_y = (float(digit.get("top", 0)) + float(digit.get("bottom", 0))) / 2
    else:
        for candidate in _digit_band_candidates(items):
            code = candidate["digits"]
            digit_left = candidate["left"]
            mid_y = float(candidate.get("mid") or 0.0)
            break
    if not code:
        return None
    edits = list(dialog.descendants(class_name="Edit"))
    best = None
    for edit in edits:
        try:
            rect = edit.rectangle()
        except Exception:
            continue
        edit_mid = (int(rect.top) + int(rect.bottom)) / 2
        if abs(edit_mid - mid_y) <= 24 and int(rect.right) <= digit_left + 30:
            best = edit
            break
    if best is None:
        return None
    return best, code


def _band_mid_y(items: list[dict], digit_left: float) -> float:
    """取 digit_left 附近数字条目的垂直中心作为水平带基准。"""
    nearby = [
        (float(i.get("top", 0)) + float(i.get("bottom", 0))) / 2
        for i in items
        if re.sub(r"\s+", "", str(i.get("text") or "")).strip().isdigit()
        and abs(float(i.get("left", 0)) - digit_left) <= 160
    ]
    return nearby[0] if nearby else 0.0



def _find_login_dialog(pids: set[int]):
    """委托登录框查找：优先含「登录」文本按钮的窗口；自绘按钮无文本时退化为
    「≥2 个 Edit 且 ≥1 个 Button」候选（华宝登录框即自绘大按钮，2026-10-26 实战）。
    """
    from pywinauto import Desktop

    # 2026-10-26 修正：xiadan 主窗也有 ≥2 Edit+Button，按识别强度降级：
    # ①按钮含「登录」文本 ②标题含「委托」（委托下单对话框，主窗标题不含） ③同带验证码数字带的最小面积窗口
    by_title = None
    fallback = None
    fallback_area = None
    for window in Desktop(backend="win32").windows():
        try:
            if window.process_id() not in pids or not window.is_visible():
                continue
            edits = list(window.descendants(class_name="Edit"))
            if len(edits) < 2:
                continue
            buttons = list(window.descendants(class_name="Button"))
            if not buttons:
                continue
            if any("登录" in str(b.window_text() or "") for b in buttons):
                return window
            title = str(window.window_text() or "")
            if "委托" in title and by_title is None:
                by_title = window
            rect = window.rectangle()
            area = max(0, int(rect.width())) * max(0, int(rect.height()))
            if fallback is None or area < fallback_area:
                fallback = window
                fallback_area = area
        except Exception:
            continue
    if by_title is not None:
        return by_title
    return fallback


def _click_login_button(dialog) -> bool:
    """点登录：优先文本含「登录」的按钮；自绘无文本时点面积最大的按钮（登录大蓝键）。"""
    best = None
    best_area = -1
    for button in dialog.descendants(class_name="Button"):
        try:
            text = str(button.window_text() or "")
            if "登录" in text and "密码" not in text:
                button.click_input()
                return True
            rect = button.rectangle()
            area = max(0, int(rect.width())) * max(0, int(rect.height()))
            if area > best_area:
                best_area = area
                best = button
        except Exception:
            continue
    if best is None:
        return False
    try:
        best.click_input()
        return True
    except Exception:
        return False


def _try_numeric_captcha(
    pids: set[int],
    submit_texts: tuple[str, ...],
    *,
    attempts: int = 2,
) -> bool:
    for _attempt in range(max(1, attempts)):
        dialog = _find_dialog_window(pids, submit_texts)
        if dialog is None:
            return False
        located = _locate_captcha(dialog)
        if located is None:
            return False
        edit, code = located
        try:
            edit.set_edit_text(code)
        except Exception:
            try:
                edit.click_input()
                edit.type_keys(code)
            except Exception:
                return False
        clicked = False
        wanted = tuple(str(value or "") for value in submit_texts if str(value or ""))
        for button in dialog.descendants(class_name="Button"):
            text = str(button.window_text() or "")
            if any(value in text for value in wanted):
                try:
                    button.click_input()
                    clicked = True
                except Exception:
                    pass
                break
        if not clicked:
            return False
        time.sleep(1.5)
        if _find_dialog_window(pids, submit_texts) is None:
            return True
    return False


def try_captcha_login(pids: set[int], *, attempts: int = 2, notes: list | None = None) -> bool:
    """登录窗数字验证码：OCR 识别→填写→点登录；失败回退调用方处理。

    2026-10-26：支持自绘登录按钮（华宝），查找与点击均有退化策略；
    notes 可传入列表收集失败原因（dialog_not_found/captcha_not_located/submitted_but_rejected）。
    """
    for _attempt in range(max(1, attempts)):
        dialog = _find_login_dialog(pids)
        if dialog is None:
            if notes is not None:
                notes.append("dialog_not_found")
            return False
        # 2026-10-27 实战：弹窗出现后验证码图有约 1s 渲染延迟，立即 OCR 会扑空
        time.sleep(0.8)
        located = None
        for _wait in range(3):
            located = _locate_captcha(dialog)
            if located is not None:
                break
            time.sleep(1.0)
        if located is None:
            if notes is not None:
                notes.append("captcha_not_located")
            return False
        edit, code = located
        # 2026-10-27：安全输入框可能吞掉 WM_SETTEXT（界面显示但程序内部未录入，服务端拒登）。
        # 改用真实键击为主，set_edit_text 仅作回退。
        try:
            edit.click_input()
            time.sleep(0.2)
            edit.type_keys(str(code), with_spaces=True)
        except Exception:
            try:
                edit.set_edit_text(str(code))
            except Exception:
                if notes is not None:
                    notes.append("captcha_write_failed")
                return False
        if not _click_login_button(dialog):
            if notes is not None:
                notes.append("login_button_not_clicked")
            return False
        time.sleep(1.5)
        if _find_login_dialog(pids) is None:
            return True
        if notes is not None:
            notes.append("submitted_but_rejected")  # 已提交但被服务端拒绝（验证码过期/站点维护）
    return False


def try_captcha_prompt(pids: set[int], *, attempts: int = 2) -> bool:
    """数字验证码提示框：拷贝保护等普通提示可自动填写并确定。"""
    return _try_numeric_captcha(pids, ("确定", "OK", "是"), attempts=attempts)
def _find_account_digits(window) -> str:
    """从对话框编辑框文本中提取资金账号（≥6 位连续数字）。"""
    for edit in window.descendants(class_name="Edit"):
        try:
            text = str(edit.window_text() or "")
        except Exception:
            continue
        digits = "".join(ch for ch in text if ch.isdigit())
        if len(digits) >= 6:
            return digits
    return ""


def password_for_fund_account(fund_account: str) -> str:
    """secrets.yaml 按资金账号精确匹配 DPAPI 密码；解密失败/未录入返回空串。"""
    from shared.config import load_secrets
    from shared.credstore import decrypt_text

    digits = "".join(ch for ch in str(fund_account) if ch.isdigit())
    if len(digits) < 6:
        return ""
    try:
        entries = (load_secrets().get("accounts_secrets") or {})
    except Exception:
        return ""
    for entry in entries.values():
        entry = entry or {}
        if str(entry.get("fund_account") or "") != digits:
            continue
        token = str(entry.get("password_enc") or "")
        if not token:
            return ""
        try:
            return decrypt_text(token)
        except Exception:
            return ""
    return ""


def _locate_password_edit(window, account_edit, captcha_edit):
    """密码框 = 非资金账号、非验证码的空 Edit（优先验证码上方的空 Edit）。"""
    candidates = []
    for edit in window.descendants(class_name="Edit"):
        if edit is account_edit or edit is captcha_edit:
            continue
        try:
            if str(edit.window_text() or "").strip():
                continue
            rect = edit.rectangle()
        except Exception:
            continue
        candidates.append((int(rect.top), edit))
    if not candidates:
        return None
    if captcha_edit is not None:
        try:
            captcha_top = int(captcha_edit.rectangle().top)
        except Exception:
            captcha_top = None
        if captcha_top is not None:
            above = [item for item in candidates if item[0] < captcha_top]
            if above:
                return max(above)[1]
    return max(candidates)[1]


def _ensure_checkbox_checked(window, text_part: str) -> None:
    for button in window.descendants(class_name="Button"):
        try:
            if text_part in str(button.window_text() or ""):
                if button.get_toggle_state() != 1:
                    button.click_input()
                return
        except Exception:
            continue


def try_password_login(pids: set[int], password: str, *, attempts: int = 2) -> bool:
    """委托登录框自动填充：资金账号(已填)→密码→保存密码→验证码→登录。

    密码仅经 WM_SETTEXT(set_edit_text) 写入密码框；任何失败返回 False 由调用方回退。
    """
    if not password:
        return False
    for _attempt in range(max(1, attempts)):
        dialog = _find_login_dialog(pids)
        if dialog is None:
            return False
        account_edit = None
        account_digits = ""
        for edit in dialog.descendants(class_name="Edit"):
            try:
                text = str(edit.window_text() or "")
            except Exception:
                continue
            digits = "".join(ch for ch in text if ch.isdigit())
            if len(digits) >= 6:
                account_edit = edit
                account_digits = digits
                break
        if not account_digits:
            return False
        located = _locate_captcha(dialog)
        captcha_edit = located[0] if located else None
        password_edit = _locate_password_edit(dialog, account_edit, captcha_edit)
        if password_edit is not None:
            try:
                password_edit.set_edit_text(str(password))
            except Exception:
                return False
        _ensure_checkbox_checked(dialog, "保存密码")
        if captcha_edit is not None:
            code = _ocr_fresh_captcha(dialog, captcha_edit)
            if not code:
                return False
            try:
                captcha_edit.set_edit_text(code)
            except Exception:
                return False
        if not _click_login_button(dialog):
            return False
        time.sleep(1.5)
        if _find_login_dialog(pids) is None:
            return True
    return False


def _ocr_fresh_captcha(dialog, captcha_edit) -> str:
    """与 captcha_edit 同水平带右侧的 4-6 位数字（沿用 _locate_captcha 的 OCR 几何关系）。"""
    located = _locate_captcha(dialog)
    if located is None:
        return ""
    edit, code = located
    try:
        same_band = abs(int(edit.rectangle().top) - int(captcha_edit.rectangle().top)) <= 24
    except Exception:
        same_band = edit is captcha_edit
    return str(code) if (same_band or edit is captcha_edit) else ""
