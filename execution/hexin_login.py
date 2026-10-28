# AI-SUMMARY: hexin 主客户端右上角账户菜单逐户登录——姓名/别名匹配可登录账户，

# 需密码/验证码行跳过；误点委托登录框立即关闭并继续，不在本模块提交委托。

import subprocess

import time

from collections.abc import Mapping



from execution.account_session import (

    AccountSessionResult,

    STATUS_ALREADY_LOGGED_IN,

    STATUS_AMBIGUOUS,

    STATUS_CONFIG_MISSING,

    STATUS_DIALOG_CLOSED,

    STATUS_DIALOG_REQUIRED,

    STATUS_LOGIN_REQUIRED,

    STATUS_MENU_FAILED,

    STATUS_NOT_SELECTED,

    STATUS_NOT_LOGGED_IN,

    STATUS_READY,

    STATUS_WRONG_ACCOUNT,

)

from execution.client_registry import ClientSpec

from execution.window_scope import pids_for_executable

from shared.errors import AutoIpoError

from shared.paths import resolve_path, runtime_path



MENU_TITLE = "Menu"

IGNORED_DIALOG_TITLES = {"about:blank", "blank", "menu", "网上股票交易系统"}

MANUAL_DIALOG_KEYWORDS = ("密码", "验证码", "动态口令", "短信验证", "身份验证", "人工处理", "安全验证")

LOGIN_DIALOG_DEFAULT_TITLE = "委托下单"

LOGIN_DIALOG_DEFAULT_KEYWORDS = ("资金账号", "资金帐号", "交易密码", "验证码")

DIALOG_ACCOUNT_KEYWORDS = ("资金账号", "资金帐号", "证券公司")

DIALOG_SECRET_KEYWORDS = ("交易密码", "密码", "验证码", "动态口令", "短信验证")





def _dialog_text(title: str, control_texts: list[str] | None) -> str:

    return "|".join([str(title or "")] + [str(item or "") for item in (control_texts or [])])





def _dialog_structure(title: str, control_texts: list[str] | None) -> dict:

    joined = _dialog_text(title, control_texts)

    return {

        "account": any(value in joined for value in ("资金账号", "资金帐号")),

        "password": "交易密码" in joined,

        "captcha": any(value in joined for value in ("验证码", "动态口令", "短信验证")),

        "action": any(value in joined for value in ("登录", "登入")),

    }





def is_login_dialog(title: str, control_texts: list[str] | None = None,

                    settings: dict | None = None) -> bool:

    """结构优先：委托下单标题，或资金账号+交易密码+验证码/登录表单。"""

    cfg = settings or {}

    title_value = str(title or "").strip()

    login_title = str(cfg.get("login_dialog_title") or LOGIN_DIALOG_DEFAULT_TITLE)

    if title_value and login_title in title_value:

        return True

    structure = _dialog_structure(title_value, control_texts)

    return structure["account"] and structure["password"] and (

        structure["captcha"] or structure["action"]

    )





def requires_manual_intervention(title: str, control_texts: list[str],

                                 settings: dict | None = None) -> bool:

    if is_login_dialog(title, control_texts, settings):

        return False

    return is_manual_dialog(title, control_texts)





def is_manual_dialog(title: str, control_texts: list[str] | None = None) -> bool:

    value = str(title or "").strip()

    if not value or value.lower() in IGNORED_DIALOG_TITLES or value in IGNORED_DIALOG_TITLES:

        return False

    joined = _dialog_text(value, control_texts)

    return any(keyword in joined for keyword in MANUAL_DIALOG_KEYWORDS)





def dialog_kind(title: str, control_texts: list[str] | None = None,

                settings: dict | None = None) -> str:

    if is_login_dialog(title, control_texts, settings):

        return "login"

    if requires_manual_intervention(title, list(control_texts or []), settings):

        return "manual"

    return ""





def _hexin_pids(client: ClientSpec | None = None) -> set[int]:

    if client is None:

        out = subprocess.run(["tasklist", "/fi", "imagename eq hexin.exe", "/fo", "csv", "/nh"],

                             capture_output=True, text=True, errors="ignore").stdout or ""

        return {int(line.split('","')[1].strip('"')) for line in out.splitlines() if '","' in line}

    return pids_for_executable(client.hexin_path)





def _login_settings(settings: dict | None = None) -> dict:

    if settings is not None:

        return settings

    from shared.config import load_config

    return (load_config().get("gui") or {}).get("hexin_login") or {}





def find_hexin_hwnd(client: ClientSpec | None = None):
    """主窗识别：先严格匹配 "同花顺(" 前缀；失败再兜底"标题含同花顺且非对话框类"。"""
    import win32gui
    import win32process
    pids = _hexin_pids(client)
    strict = []
    loose = []

    def cb(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return
            _, procpid = win32process.GetWindowThreadProcessId(hwnd)
            if int(procpid) not in pids:
                return
            title = win32gui.GetWindowText(hwnd)
            if title.startswith("同花顺("):
                strict.append(hwnd)
            elif "同花顺" in title and win32gui.GetClassName(hwnd) != "#32770":
                l, t, r, b = win32gui.GetWindowRect(hwnd)
                if (r - l) >= 800 and (b - t) >= 500:  # 主窗至少接近全屏；启动小窗/弹窗不算
                    loose.append(hwnd)
        except Exception:
            pass
    win32gui.EnumWindows(cb, None)
    result = strict or loose
    if len(result) > 1 and client is not None:
        raise AutoIpoError(
            "HEXIN_WINDOW_AMBIGUOUS",
            f"找到 {len(result)} 个同花顺主窗口",
            "关闭重复实例/残留窗口后运行 python run.py doctor",
            {"client_id": client.client_id if client else "legacy"},
        )
    return result[0] if result else None

def _restore_hexin_window(timeout: int = 30, client: ClientSpec | None = None):

    exe = client.hexin_path if client else resolve_path("E:/nonexistent/hexin.exe")

    if client is None:

        from execution.client_registry import load_client_spec

        from shared.config import load_config

        specs = [load_client_spec(load_config())]

        if len(specs) != 1:

            raise AutoIpoError(

                "CLIENT_CONTEXT_REQUIRED",

                "多客户端必须显式指定 client_id",

                "传入 ClientSpec，禁止启动任意 hexin.exe",

            )

        exe = specs[0].hexin_path

    subprocess.Popen([str(exe)])

    deadline = time.time() + timeout

    while time.time() < deadline:

        hwnd = find_hexin_hwnd(client)

        if hwnd is not None:

            return hwnd

        time.sleep(1)

    return None





def bring_to_front(hwnd) -> bool:

    import win32gui

    win32gui.ShowWindow(hwnd, 9)

    win32gui.ShowWindow(hwnd, 3)

    time.sleep(0.6)

    try:

        win32gui.SetForegroundWindow(hwnd)

    except Exception:

        pass

    time.sleep(0.6)

    try:

        if win32gui.GetWindowText(win32gui.GetForegroundWindow()).startswith("同花顺("):

            return True

    except Exception:

        pass

    try:

        from pywinauto import Desktop

        for w in Desktop(backend="uia").windows():

            if w.handle == hwnd:

                w.set_focus()

                time.sleep(0.8)

                break

    except Exception:

        pass

    try:

        return win32gui.GetWindowText(win32gui.GetForegroundWindow()).startswith("同花顺(")

    except Exception:

        return False





def match_button(hwnd, settings: dict | None = None):

    import cv2

    import numpy as np

    import win32gui

    import PIL.ImageGrab as IG

    cfg = _login_settings(settings)

    tpl_path = resolve_path(str(cfg.get("button_template", "runtime_data/tpl_account_btn.png")))

    if not tpl_path.exists():

        return None

    l, t, r, b = win32gui.GetWindowRect(hwnd)

    band = (l, t, r, t + int(cfg.get("button_band_height", 30)))

    tpl = cv2.imdecode(np.fromfile(str(tpl_path), dtype=np.uint8), cv2.IMREAD_COLOR)

    shot = IG.grab(bbox=band)

    img = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)

    res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)

    _, max_val, _, max_loc = cv2.minMaxLoc(res)

    if max_val < float(cfg.get("button_threshold", 0.8)):

        return None

    return (band[0] + max_loc[0] + int(cfg.get("button_click_dx", 12)),

            band[1] + max_loc[1] + int(cfg.get("button_click_dy", 9)))





def menu_window(client: ClientSpec | None = None):

    import win32gui

    import win32process

    pids = _hexin_pids(client)

    found = []



    def cb(hwnd, _):

        try:

            if win32gui.GetWindowText(hwnd) == MENU_TITLE and win32gui.IsWindowVisible(hwnd):

                _, procpid = win32process.GetWindowThreadProcessId(hwnd)

                if int(procpid) in pids:

                    l, t, r, b = win32gui.GetWindowRect(hwnd)

                    if 0 <= l < 10000 and 0 <= t < 10000 and r > l and b > t:

                        found.append(hwnd)

        except Exception:

            pass

    win32gui.EnumWindows(cb, None)

    return found[0] if found else None





def read_menu_rows(menu_hwnd, settings: dict | None = None) -> list[dict]:

    try:

        from pywinauto import Desktop

        window = next((w for w in Desktop(backend="uia").windows() if w.handle == menu_hwnd), None)

        if window is not None:

            rows = []

            for control in window.descendants():

                try:

                    text = (control.window_text() or "").strip()

                    rect = control.rectangle()

                    if text and rect.height() > 0:

                        rows.append({

                            "index": len(rows),

                            "text": text,

                            "top": int(rect.top),

                            "bottom": int(rect.bottom),

                        })

                except Exception:

                    continue

            if rows:

                rows.sort(key=lambda item: item["top"])

                for index, row in enumerate(rows):

                    row["index"] = index

                return rows

    except Exception:

        pass



    try:

        import uuid

        import win32gui

        from PIL import ImageGrab

        from shared.username_ocr import read_menu_rows_with_ocr



        out = runtime_path("ocr", f"menu_{uuid.uuid4().hex}.png")

        out.parent.mkdir(parents=True, exist_ok=True)

        try:

            menu_rect = win32gui.GetWindowRect(menu_hwnd)

            ImageGrab.grab(menu_rect).save(out)

            items = read_menu_rows_with_ocr(out, with_positions=True)

        finally:

            out.unlink(missing_ok=True)

        rows = []

        for item in items:

            text = str(item.get("text") or "").strip()

            if not text:

                continue

            rows.append({

                "index": len(rows),

                "text": text,

                "top": int(menu_rect[1] + float(item.get("top") or 0)),

                "bottom": int(menu_rect[1] + float(item.get("bottom") or 0)),

            })

        return rows

    except Exception:

        return []





def _norm(value: str) -> str:

    return "".join((value or "").split()).replace("－", "-").lower()





def _target_aliases(target: dict) -> list[str]:

    values = [target.get("display_name"), target.get("id"), target.get("alias")]

    aliases = target.get("aliases") or []

    values.extend(aliases if isinstance(aliases, list) else [aliases])

    return [str(value).strip() for value in values if str(value or "").strip()]





def _has_name_or_alias_feature(value: str) -> bool:

    compact = _norm(value)

    return len(compact) >= 2 and not compact.isdigit()





def _row_target_matches(target: dict, text: str) -> bool:

    row = _norm(text)

    base = row.removesuffix("已登录").removesuffix("f12").removesuffix("登录")

    for alias in _target_aliases(target):

        value = _norm(alias)

        if not _has_name_or_alias_feature(alias):

            continue

        if value in {row, base}:

            return True

        if base.endswith(value):

            prefix = base[:-len(value)]

            if not prefix or prefix[-1].isspace() or prefix[-1] in "-_｜|·/\\":

                return True

    return False





def _row_fund_hashes(text: str) -> set[str]:

    import re

    from execution.account_session import hash_fund_account

    return {hash_fund_account(value) for value in re.findall(r"\d{6,}", str(text or ""))}





def _classify_rows(targets: list[dict], rows: list[dict]) -> dict[int, dict]:

    classified: dict[int, dict] = {}

    for row_index, row in enumerate(rows or []):

        index = int(row.get("index", row_index))

        text = str(row.get("text", ""))

        matched = [target for target in targets if _row_target_matches(target, text)]

        if len(matched) == 1:

            classified[index] = {"kind": "direct", "target": matched[0]}

            continue

        if len(matched) > 1:

            classified[index] = {"kind": "ambiguous", "targets": matched}

            continue

        hashes = _row_fund_hashes(text)

        hash_matches = [target for target in targets

                        if target.get("fund_account_hash") in hashes]

        if len(hash_matches) == 1:

            classified[index] = {"kind": "login_required", "target": hash_matches[0]}

        elif len(hash_matches) > 1:

            classified[index] = {"kind": "ambiguous", "targets": hash_matches}

        elif any(str(target.get("broker", "")).strip() and

                 _norm(str(target.get("broker", ""))) == _norm(text)

                 for target in targets):

            broker_matches = [target for target in targets

                              if _norm(str(target.get("broker", ""))) == _norm(text)]

            classified[index] = (

                {"kind": "login_required", "target": broker_matches[0]}

                if len(broker_matches) == 1

                else {"kind": "ambiguous", "targets": broker_matches}

            )

        elif "证券" in text and any(char.isdigit() for char in text):

            classified[index] = {"kind": "login_required", "target": None}

        else:

            classified[index] = {"kind": "other", "target": None}

    return classified





def resolve_menu_row(target: dict, rows: list[dict], *, cached_row: int | None = None,

                     configured_row: int | None = None, max_rows: int | None = None):

    """按文本唯一匹配；menu_row 只在多个同名行中做辅助选择，不生成盲点候选。"""

    if configured_row is None:

        configured_row = target.get("menu_row")

    matches = [int(row.get("index", index)) for index, row in enumerate(rows or [])

               if _row_target_matches(target, str(row.get("text", "")))]

    if len(matches) == 1:

        return matches[0], "text"

    if len(matches) > 1:

        for source, row in (("cache", cached_row), ("config", configured_row)):

            if row is not None and int(row) in matches:

                return int(row), source

        return None, "ambiguous"

    return None, "none"





def _default_open_menu(settings: dict | None = None, client: ClientSpec | None = None):

    import pywinauto.mouse as m

    cfg = _login_settings(settings)

    hwnd = find_hexin_hwnd(client)
    for _ in range(2):
        if hwnd is not None:
            break
        time.sleep(1)
        hwnd = find_hexin_hwnd(client)
    if hwnd is None:
        hwnd = _restore_hexin_window(client=client)

    if hwnd is None:

        raise RuntimeError("找不到 hexin 主客户端窗口")

    last_err = "按钮模板未匹配"

    for _ in range(int(cfg.get("button_attempts", 3))):

        if not bring_to_front(hwnd):

            last_err = "hexin 未能置为前台窗口"

            continue

        xy = match_button(hwnd, cfg)

        if xy is None:

            last_err = f"账户下拉按钮模板未匹配（阈值{cfg.get('button_threshold', 0.8)}）"

            continue

        m.click(coords=xy)

        deadline = time.time() + float(cfg.get("menu_wait_s", 5))

        while time.time() < deadline:

            menu = menu_window(client)

            if menu is not None:

                return menu

            time.sleep(0.4)

        last_err = "点击后菜单未弹出"

    raise RuntimeError(f"打开账户下拉菜单失败：{last_err}")





def _menu_metrics(menu_hwnd, rows: list[dict], settings: dict):

    import win32gui

    l, t, r, b = win32gui.GetWindowRect(menu_hwnd)

    height = b - t

    row_count = len(rows)

    if row_count <= 0:

        calibrated_h = max(1, int(settings.get("row_height", 26)))

        row_count = max(1, round((height - int(settings.get("row_first_offset", 19))) / calibrated_h))

    row_height = (height - int(settings.get("row_first_offset", 19))) / row_count

    return {"left": l, "top": t, "height": height, "row_count": row_count, "row_height": row_height}





def _default_click_row(menu_hwnd, row: int, total_rows: int, settings: dict | None = None):

    import pywinauto.mouse as m

    cfg = _login_settings(settings)

    row_info = row if isinstance(row, Mapping) else {}

    click_x = row_info.get("click_x")
    click_y = row_info.get("click_y")
    if isinstance(click_x, (int, float)) and isinstance(click_y, (int, float)):
        m.click(coords=(int(click_x), int(click_y)))
        return

    metrics = _menu_metrics(menu_hwnd, [], cfg)

    row_index = int(row_info.get("index", row) if row_info else row)

    row_count = max(1, total_rows or metrics["row_count"])  # 0=无 UIA 文本，按菜单高度+校准行高推断总行数

    # 同花顺账户区固定行高；总行数包含底部分隔线和工具项，不能据此摊薄账户行高。

    row_height = float(cfg.get("row_height", 26))

    if row_index < 0 or row_index >= row_count:

        raise RuntimeError(f"菜单行号越界：{row_index}/{row_count}")

    x = metrics["left"] + int(cfg.get("row_x_offset", 116))

    top = row_info.get("top")

    bottom = row_info.get("bottom")

    if isinstance(top, (int, float)) and isinstance(bottom, (int, float)) and bottom > top:

        y = int((top + bottom) / 2)

    else:

        y = metrics["top"] + int(cfg.get("row_first_offset", 19)) + int(row_height * row_index)

    m.click(coords=(x, y))





def _default_xiadan_labels(client: ClientSpec | None = None) -> list[str]:

    from execution.login import logged_in_labels

    return logged_in_labels(client)





def _default_account_state(account_id: str, client: ClientSpec | None = None):

    from execution.login import account_session_state

    return account_session_state(account_id, client=client).as_dict()





def _safe_dialog_value(value: str) -> str:

    import re

    return re.sub(r"\d{6,}", "[资金账号已脱敏]", str(value or ""))





def _safe_dialog_texts(title: str, control_texts: list[str]) -> list[str]:

    return [_safe_dialog_value(value) for value in [title, *control_texts] if str(value or "").strip()]





def _default_dialog_records(client: ClientSpec | None = None,

                            settings: dict | None = None) -> list[dict]:

    import win32gui

    import win32process

    cfg = _login_settings(settings)

    out = []

    for kind_name in ("hexin", "xiadan", "xiadan-plus"):

        if kind_name == "hexin":

            pids = _hexin_pids(client)

        elif kind_name == "xiadan":

            if client is not None:

                from execution.login import _xiadan_pids

                pids = _xiadan_pids(client)

            else:

                r = subprocess.run(["tasklist", "/fi", "imagename eq xiadan.exe", "/fo", "csv", "/nh"],

                                   capture_output=True, text=True, errors="ignore").stdout or ""

                pids = {int(line.split('","')[1].strip('"')) for line in r.splitlines() if '","' in line}

        else:

            if client is not None:

                plus_path = client.xiadan_path.parent / "xiadan-plus" / "xiadan-plus.exe"

                pids = pids_for_executable(plus_path)

            else:

                r = subprocess.run(["tasklist", "/fi", "imagename eq xiadan-plus.exe", "/fo", "csv", "/nh"],

                                   capture_output=True, text=True, errors="ignore").stdout or ""

                pids = {int(line.split('","')[1].strip('"')) for line in r.splitlines() if '","' in line}



        def cb(hwnd, _):

            try:

                if not win32gui.IsWindowVisible(hwnd):

                    return

                _, procpid = win32process.GetWindowThreadProcessId(hwnd)

                if int(procpid) not in pids:

                    return

                title = win32gui.GetWindowText(hwnd) or ""

                texts = []



                def collect(child, _):

                    class_name = str(win32gui.GetClassName(child) or "").lower()

                    if any(name in class_name for name in ("edit", "combobox")):

                        return

                    texts.append(win32gui.GetWindowText(child) or "")



                win32gui.EnumChildWindows(hwnd, collect, None)

                kind = dialog_kind(title, texts, cfg)

                if kind:

                    out.append({

                        "hwnd": int(hwnd),

                        "title": _safe_dialog_value(title),

                        "kind": kind,

                        "texts": _safe_dialog_texts(title, texts),

                    })

            except Exception:

                pass

        win32gui.EnumWindows(cb, None)



    seen = {int(item.get("hwnd") or 0) for item in out}

    login_title = str(cfg.get("login_dialog_title") or LOGIN_DIALOG_DEFAULT_TITLE)



    def global_cb(hwnd, _):

        try:

            if not win32gui.IsWindowVisible(hwnd) or int(hwnd) in seen:

                return

            title = win32gui.GetWindowText(hwnd) or ""

            if login_title not in title:

                return

            texts = []



            def collect(child, _):

                class_name = str(win32gui.GetClassName(child) or "").lower()

                if any(name in class_name for name in ("edit", "combobox")):

                    return

                texts.append(win32gui.GetWindowText(child) or "")



            win32gui.EnumChildWindows(hwnd, collect, None)

            kind = dialog_kind(title, texts, cfg)

            if kind:

                out.append({

                    "hwnd": int(hwnd),

                    "title": _safe_dialog_value(title),

                    "kind": kind,

                    "texts": _safe_dialog_texts(title, texts),

                })

        except Exception:

            pass



    win32gui.EnumWindows(global_cb, None)

    return out





def _default_dialogs(client: ClientSpec | None = None,

                     settings: dict | None = None) -> list[dict]:

    return _default_dialog_records(client, settings)





def detect_manual_dialogs(client: ClientSpec | None = None) -> list[str]:

    return [item["title"] for item in _default_dialog_records(client)

            if item.get("kind") == "manual"]





def _default_close_login_dialog(dialogs: list[dict], settings: dict | None = None,

                                client: ClientSpec | None = None) -> bool:

    import win32gui

    items = [item for item in dialogs if isinstance(item, dict) and int(item.get("hwnd") or 0)]

    if not items:

        items = [item for item in _default_dialog_records(client, settings)

                 if item.get("kind") == "login"]

    closed = False

    for item in items:

        hwnd = int(item.get("hwnd") or 0)

        if hwnd and win32gui.IsWindow(hwnd):

            win32gui.PostMessage(hwnd, 0x0010, 0, 0)  # WM_CLOSE

            closed = True

    return closed





def _default_shot(name: str):

    import PIL.ImageGrab as IG

    out = runtime_path(name)

    out.parent.mkdir(parents=True, exist_ok=True)

    IG.grab().save(str(out))





def _default_close_menu():

    import pywinauto.keyboard as kb

    kb.send_keys("{ESC}")





def _safe_label(value: str) -> str:

    import re

    def mask(match):

        digits = match.group(0)

        return f"{digits[:3]}****{digits[-4:]}"

    return re.sub(r"\d{6,}", mask, str(value or ""))





def _session(target: dict, **updates) -> AccountSessionResult:

    data = {

        "account_id": target["id"],

        "display_name": _safe_label(target.get("display_name") or ""),

        "fund_account_hash": target.get("fund_account_hash") or "",

        "status": STATUS_NOT_LOGGED_IN,

        "client_id": target.get("client_id", ""),

    }

    data.update(updates)

    for key in ("display_name", "current_fund_account", "error"):

        if key in data:

            data[key] = _safe_label(data[key])

    return AccountSessionResult(**data)





def _dialog_items(raw) -> list[dict]:

    items = []

    for value in list(raw or []):

        if isinstance(value, dict):

            items.append({

                "hwnd": int(value.get("hwnd") or 0),

                "title": str(value.get("title") or ""),

                "kind": str(value.get("kind") or ""),

                "texts": list(value.get("texts") or []),

            })

        else:

            title = str(value or "")

            items.append({"hwnd": 0, "title": title, "kind": "", "texts": [title]})

    return items





def _partition_dialogs(raw, settings: dict) -> tuple[list[dict], list[dict]]:

    login, manual = [], []

    for item in _dialog_items(raw):

        kind = dialog_kind(item["title"], item.get("texts"), settings) or item.get("kind")

        if kind == "login":

            login.append(item)

        elif kind == "manual":

            manual.append(item)

    return login, manual





def login_accounts(targets: list[dict], *, _open_menu=None, _read_rows=None, _click_row=None,

                   _account_state=None, _xiadan_labels=None, _dialogs=None, _shot=None,

                   _close_menu=None, _sleep=None, _close_login_dialog=None,

                   max_attempts: int = 1, settings: dict | None = None,

                   client: ClientSpec | None = None) -> list[AccountSessionResult]:

    """只点唯一姓名/别名匹配行；需登录行默认跳过，误点委托登录框立即关闭后继续。"""

    cfg = _login_settings(settings)

    open_menu = _open_menu or (lambda: _default_open_menu(cfg, client))

    read_rows = _read_rows or read_menu_rows

    click_row = _click_row or (lambda menu, row, total: _default_click_row(menu, row, total, cfg))

    account_state = _account_state or (lambda account_id: _default_account_state(account_id, client))

    labels = _xiadan_labels or (lambda: _default_xiadan_labels(client))

    dialogs = _dialogs or (lambda: _default_dialogs(client, cfg))

    shot = _shot or _default_shot

    close_menu = _close_menu or _default_close_menu

    close_login_dialog = _close_login_dialog or (

        lambda items: _default_close_login_dialog(items, cfg, client)

    )

    sleep = _sleep or time.sleep

    max_total = int(cfg.get("max_accounts", 10))

    close_enabled = bool(cfg.get("close_login_dialog", True))



    for target in targets:

        target.setdefault("client_id", client.client_id if client else "")

    results_by_id: dict[str, AccountSessionResult] = {}

    try:

        initial_labels = [item for item in list(labels()) if str(item or "").strip()]

    except Exception:

        initial_labels = []

    logged_count = len(set(initial_labels))

    need: list[dict] = []

    for target in targets:

        matched_label = next((item for item in initial_labels if _row_target_matches(target, item)), "")

        state = account_state(target["id"]) or {}

        expected_hash = target.get("fund_account_hash") or state.get("fund_account_hash") or ""

        hash_ok = bool(expected_hash) and state.get("fund_account_hash") == expected_hash

        if matched_label and not expected_hash:

            results_by_id[target["id"]] = _session(

                target, status=STATUS_CONFIG_MISSING, error="账户资金账号哈希缺失，拒绝把标签当已登录",

            )

        elif matched_label and hash_ok:

            results_by_id[target["id"]] = _session(

                target,

                display_name=matched_label or state.get("display_name") or target.get("display_name") or target["id"],

                fund_account_hash=expected_hash,

                xiadan_present=True,

                current_fund_account=state.get("current_fund_account", ""),

                status=STATUS_ALREADY_LOGGED_IN,

            )

        elif matched_label:

            results_by_id[target["id"]] = _session(

                target,

                display_name=matched_label,

                fund_account_hash=state.get("fund_account_hash", ""),

                xiadan_present=bool(state.get("xiadan_present")),

                current_fund_account=state.get("current_fund_account", ""),

                status=STATUS_WRONG_ACCOUNT,

                error="账户标签匹配但资金账号哈希不符",

            )

        elif state.get("xiadan_present") and hash_ok:

            results_by_id[target["id"]] = _session(

                target,

                display_name=state.get("display_name") or target.get("display_name") or target["id"],

                fund_account_hash=expected_hash,

                xiadan_present=True,

                current_fund_account=state.get("current_fund_account", ""),

                status=STATUS_ALREADY_LOGGED_IN,

            )

        else:

            need.append(target)

    logged_count = max(logged_count, sum(

        item.status == STATUS_ALREADY_LOGGED_IN for item in results_by_id.values()

    ))



    def finish_unselected(reason: str):

        for target in need:

            results_by_id.setdefault(

                target["id"],

                _session(target, status=STATUS_NOT_SELECTED, error=reason),

            )



    pre_login, pre_manual = _partition_dialogs(dialogs(), cfg)

    if pre_manual:

        titles = "；".join(_safe_label(item["title"]) for item in pre_manual)

        shot("boot_login/dialog_manual.png")

        reason = f"人工处理：身份验证/安全弹窗（{titles}）"

        for target in need:

            results_by_id.setdefault(target["id"], _session(target, status=STATUS_DIALOG_REQUIRED, error=reason))

        return [results_by_id[target["id"]] for target in targets]

    if pre_login and close_enabled:

        closed = close_login_dialog(pre_login)

        sleep(float(cfg.get("dialog_close_wait_s", 0.5)))

        remaining_login, remaining_manual = _partition_dialogs(dialogs(), cfg)

        if not closed or remaining_login or remaining_manual:

            reason = "人工处理：预存在委托下单登录框关闭失败"

            for target in need:

                results_by_id.setdefault(target["id"], _session(target, status=STATUS_DIALOG_REQUIRED, error=reason))

            return [results_by_id[target["id"]] for target in targets]

    elif pre_login:

        reason = "人工处理：委托下单登录框未配置自动关闭"

        for target in need:

            results_by_id.setdefault(target["id"], _session(target, status=STATUS_DIALOG_REQUIRED, error=reason))

        return [results_by_id[target["id"]] for target in targets]



    if not need:

        return [results_by_id[target["id"]] for target in targets]

    if logged_count >= max_total:

        finish_unselected("已达单实例登录上限")

        return [results_by_id[target["id"]] for target in targets]



    menu = None

    try:

        menu = open_menu()

        rows = list(read_rows(menu) or [])

        shot("boot_login/menu.png")

    except Exception as exc:

        finish_unselected(f"账户菜单读取失败：{str(exc)[:100]}")

        return [results_by_id[target["id"]] for target in targets]



    classified = _classify_rows(targets, rows)

    direct_by_target: dict[str, list[int]] = {}

    for row, info in classified.items():

        if info["kind"] == "direct":

            direct_by_target.setdefault(info["target"]["id"], []).append(row)

        elif info["kind"] == "login_required" and info.get("target"):

            target = info["target"]

            if any(item["id"] == target["id"] for item in need) and target["id"] not in results_by_id:

                results_by_id[target["id"]] = _session(

                    target, main_menu_row=row, status=STATUS_LOGIN_REQUIRED,

                    error="菜单仅证券公司+资金账号，需填写密码/验证码，默认跳过",

                )

        elif info["kind"] == "ambiguous" and info.get("targets"):

            for target in info["targets"]:

                if any(item["id"] == target["id"] for item in need) and target["id"] not in results_by_id:

                    results_by_id[target["id"]] = _session(

                        target, main_menu_row=row, status=STATUS_AMBIGUOUS,

                        error="账户菜单行无法唯一匹配，不点击",

                    )



    pending: list[tuple[dict, int]] = []

    for target in need:

        if target["id"] in results_by_id:

            continue

        rows_for_target = direct_by_target.get(target["id"], [])

        if not rows_for_target:

            results_by_id[target["id"]] = _session(

                target, status=STATUS_NOT_SELECTED,

                error="菜单中无唯一姓名/别名匹配的可直接登录行",

            )

            continue

        if len(rows_for_target) > 1:

            cached = target.get("menu_row")

            chosen = int(cached) if cached is not None and int(cached) in rows_for_target else None

            if chosen is None:

                results_by_id[target["id"]] = _session(

                    target, status=STATUS_AMBIGUOUS,

                    error="多个菜单行匹配同一账户，不使用 menu_row 盲点",

                )

                continue

            row = chosen

        else:

            row = rows_for_target[0]

        if logged_count + len(pending) >= max_total:

            results_by_id[target["id"]] = _session(

                target, main_menu_row=row, status=STATUS_NOT_SELECTED,

                error="已达单实例登录上限",

            )

            continue

        pending.append((target, row))



    aborted = None

    for target, row in pending:

        if aborted:

            results_by_id[target["id"]] = _session(target, status=STATUS_DIALOG_REQUIRED, error=aborted)

            continue

        try:

            before = set(labels())

            for _attempt in range(max(1, int(max_attempts))):

                click_row(menu, row, len(rows))

                menu = None

                post_login, post_manual = _partition_dialogs(dialogs(), cfg)

                if post_manual:

                    titles = "；".join(_safe_label(item["title"]) for item in post_manual)

                    shot(f"boot_login/dialog_manual_{target['id']}.png")

                    aborted = f"人工处理：身份验证/安全弹窗（{titles}）"

                    results_by_id[target["id"]] = _session(

                        target, main_menu_row=row, status=STATUS_DIALOG_REQUIRED, error=aborted,

                    )

                    break

                if post_login:

                    if not close_enabled:

                        aborted = "人工处理：委托下单登录框未配置自动关闭"

                        results_by_id[target["id"]] = _session(

                            target, main_menu_row=row, status=STATUS_DIALOG_REQUIRED, error=aborted,

                        )

                        break

                    shot(f"boot_login/dialog_login_{target['id']}.png")

                    close_login_dialog(post_login)

                    sleep(float(cfg.get("dialog_close_wait_s", 0.5)))

                    remaining_login, remaining_manual = _partition_dialogs(dialogs(), cfg)

                    if remaining_login or remaining_manual:

                        aborted = "人工处理：委托下单登录框关闭失败"

                        results_by_id[target["id"]] = _session(

                            target, main_menu_row=row, status=STATUS_DIALOG_REQUIRED, error=aborted,

                        )

                        break

                    results_by_id[target["id"]] = _session(

                        target, main_menu_row=row, status=STATUS_DIALOG_CLOSED,

                        error="误点需登录账户，委托下单登录框已关闭；未填写密码/验证码",

                    )

                    break

                state = account_state(target["id"]) or {}

                new_labels = [item for item in labels() if item not in before]

                expected_hash = target.get("fund_account_hash") or state.get("fund_account_hash") or ""

                target_label = next((item for item in new_labels if _row_target_matches(target, item)), "")

                hash_ok = bool(expected_hash) and state.get("fund_account_hash") == expected_hash

                if hash_ok:

                    results_by_id[target["id"]] = _session(

                        target,

                        display_name=target_label or state.get("display_name") or target.get("display_name") or target["id"],

                        fund_account_hash=expected_hash,

                        main_menu_row=row,

                        xiadan_present=True,

                        current_fund_account=state.get("current_fund_account", ""),

                        status=STATUS_READY,

                    )

                    logged_count += 1

                    break

                wrong_label = next((item for item in new_labels if not _row_target_matches(target, item)), "")

                if wrong_label or (state.get("xiadan_present") and expected_hash and

                                   state.get("fund_account_hash") not in {"", expected_hash}):

                    actual = wrong_label or state.get("display_name") or "未知账户"

                    shot(f"boot_login/wrong_row_{target['id']}.png")

                    results_by_id[target["id"]] = _session(

                        target,

                        display_name=actual,

                        fund_account_hash=state.get("fund_account_hash", ""),

                        main_menu_row=row,

                        xiadan_present=bool(state.get("xiadan_present")),

                        current_fund_account=state.get("current_fund_account", ""),

                        status=STATUS_WRONG_ACCOUNT,

                        error=f"点第{row}行实际登录：{_safe_label(actual)}",

                    )

                    break

                if menu is None:

                    menu = open_menu()

                    rows = list(read_rows(menu) or [])

                sleep(float(cfg.get("login_wait_s", 15)))

            else:

                results_by_id[target["id"]] = _session(

                    target, main_menu_row=row, status=STATUS_NOT_SELECTED,

                    error="点击后未能确认目标账户，禁止继续切换",

                )

        except Exception as exc:

            results_by_id[target["id"]] = _session(

                target, main_menu_row=row, status=STATUS_MENU_FAILED, error=str(exc)[:100],

            )



    finish_unselected("登录流程提前结束")

    try:

        close_menu()

    except Exception:

        pass

    return [results_by_id[target["id"]] for target in targets]




