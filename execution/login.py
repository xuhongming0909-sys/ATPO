# AI-SUMMARY: 同花顺下单客户端启动与换户——xiadan 必须由 hexin 主客户端 F12 带会话令牌启动

# （裸启动=游客态，看不到记住的账户且被「未注册用户」弹窗挡死）；多账户切换=顶栏账户下拉

# 真实点行（select() 只改显示不换上下文），成功判据=资金账号 ComboBox 刷新；附模态框清理与实盘截图留痕。

# 废弃的登录框自动化（选券商/密码/验证码OCR）归档于 execution/legacy_login_dialog.py。

import json

import subprocess

import time

from pathlib import Path



from pywinauto import Desktop

from pywinauto.mouse import click as mouse_click



from execution.account_session import (

    AccountSessionResult,

    STATUS_DIALOG_REQUIRED,

    STATUS_NOT_LOGGED_IN,

    STATUS_READY,

    STATUS_WRONG_ACCOUNT,

    STATUS_XIADAN_FAILED,

    hash_fund_account,

    mask_fund_account,

)

from execution.client_registry import ClientSpec

from execution.window_scope import pids_for_executable, require_single_window, windows_for_pids

from shared.config import load_config, load_secrets

from shared.errors import AutoIpoError, sanitize_sensitive_text

from shared.paths import runtime_path



LOGIN_BTN = "登录"

CACHE_VERSION = 2


def _client_id(client: ClientSpec | None) -> str:
    return client.client_id if client else ""


def _account_cache_path() -> Path:

    return runtime_path("account_map.json")





def _load_account_cache() -> dict:

    """读取脱敏账户缓存；兼容旧版完整资金账号键并立即内存迁移。"""

    cache_file = _account_cache_path()

    try:

        raw = json.loads(cache_file.read_text(encoding="utf-8"))

    except Exception:

        return {"version": CACHE_VERSION, "accounts": {}}

    if raw.get("version") == CACHE_VERSION and isinstance(raw.get("accounts"), dict):

        return raw

    accounts = {}

    for fund_account, display_name in (raw or {}).items():

        if not str(fund_account).isdigit():

            continue

        accounts[hash_fund_account(str(fund_account))] = {

            "display_name": display_name,

            "fund_account_masked": mask_fund_account(str(fund_account)),

        }

    return {"version": CACHE_VERSION, "accounts": accounts}





def _write_account_cache(cache: dict) -> None:

    payload = {"version": CACHE_VERSION, "accounts": cache.get("accounts", {})}

    cache_file = _account_cache_path()

    cache_file.parent.mkdir(parents=True, exist_ok=True)

    cache_file.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")





def save_account_cache_entry(fund_account: str, display_name: str, menu_row: int | None = None,

                             client_id: str = "") -> None:

    cache = _load_account_cache()

    key = f"{client_id}|{hash_fund_account(fund_account)}" if client_id else hash_fund_account(fund_account)

    cache["accounts"][key] = {

        "display_name": display_name,

        "fund_account_masked": mask_fund_account(fund_account),

        "menu_row": menu_row,

        "client_id": client_id,

    }

    _write_account_cache(cache)





def _cache_key(fund_account: str, client_id: str = "") -> str:

    return f"{client_id}|{hash_fund_account(fund_account)}" if client_id else hash_fund_account(fund_account)





def get_cached_display_name(fund_account: str, client_id: str = "") -> str:

    entry = _load_account_cache()["accounts"].get(_cache_key(fund_account, client_id)) or {}

    return str(entry.get("display_name") or "")





def get_cached_menu_row(fund_account: str, client_id: str = "") -> int | None:

    entry = _load_account_cache()["accounts"].get(_cache_key(fund_account, client_id)) or {}

    row = entry.get("menu_row")

    return int(row) if row is not None else None





def _pids(image: str) -> set[str]:

    out = subprocess.run(["tasklist", "/fi", f"imagename eq {image}", "/fo", "csv", "/nh"],

                         capture_output=True, text=True, errors="ignore").stdout or ""

    pids = set()

    for line in out.splitlines():

        parts = line.split('","')

        if len(parts) > 1 and parts[0].strip('"').lower() == image.lower():

            pids.add(parts[1].strip('"'))

    return pids





def _xiadan_pids(client: ClientSpec | None = None) -> set[int]:

    if client is None:

        return {int(pid) for pid in _pids("xiadan.exe")}

    return pids_for_executable(client.xiadan_path)





def _find_window(pids: set[str], class_prefix: str, title_has: str = "", visible_only: bool = True):

    for w in Desktop(backend="win32").windows():

        try:

            if int(w.process_id()) not in pids:

                continue

            if visible_only and not w.is_visible():

                continue

            if class_prefix and not w.class_name().startswith(class_prefix):

                continue

            if title_has and title_has not in w.window_text():

                continue

            return w

        except Exception:

            continue

    return None





def _hexin_main_window(client: ClientSpec | None = None):

    """同花顺主客户端主窗（标题形如「同花顺(9.60.71) - 自选股」，可能在托盘导致窗口藏屏外）。"""

    pids = ({int(pid) for pid in _pids("hexin.exe")} if client is None

            else pids_for_executable(client.hexin_path))

    windows = windows_for_pids(pids, class_prefix="Afx", title_has="同花顺(", visible_only=False)

    return (require_single_window(windows, client.client_id, "hexin 主窗") if client and windows

            else (windows[0] if windows else None))





def _launch_xiadan_via_f12(xiadan_path: str, timeout: int = 40, client: ClientSpec | None = None) -> None:

    """xiadan 没在跑才启动，通过 hexin 主客户端 F12 带令牌启动（裸启动是游客态，无法交易）。



    进程在但没有任何窗口时不得强杀；报告人工处理，避免误伤正在启动或托盘隐藏的客户端。

    """

    if _xiadan_pids(client):

        if _main_window(client) is not None or _login_dialog(client) is not None:

            return

        time.sleep(5)  # 可能正在启动中，再确认一次

        if _main_window(client) is not None or _login_dialog(client) is not None:

            return

        raise AutoIpoError(

            "CLIENT_PREEXISTING_UNRESPONSIVE",

            "指定 xiadan 进程存在但未发现窗口",

            "人工确认该进程后关闭或等待其完成启动；程序不会强制结束进程",

            {"client_id": client.client_id if client else "legacy", "pids": sorted(_xiadan_pids(client))},

        )

    hexin_pids = ({int(pid) for pid in _pids("hexin.exe")} if client is None

                  else pids_for_executable(client.hexin_path))

    if not hexin_pids:

        hexin_path = Path(xiadan_path).with_name("hexin.exe")

        subprocess.Popen([str(hexin_path)])

        deadline = time.time() + 60

        while time.time() < deadline and _hexin_main_window(client) is None:

            time.sleep(2)

        time.sleep(10)  # 等主客户端自身完成同花顺账号自动登录

    hexin = _hexin_main_window(client)

    if hexin is None:

        raise AutoIpoError(

            "HEXIN_WINDOW_MISSING",

            "找不到指定同花顺主客户端窗口",

            "启动对应 hexin.exe，或运行 python run.py doctor 检查客户端路径/进程归属",

            {"client_id": client.client_id if client else "legacy"},

        )

    hexin.restore()

    time.sleep(1.5)

    hexin.set_focus()

    time.sleep(0.5)

    hexin.type_keys("{F12}")

    deadline = time.time() + timeout

    while time.time() < deadline:

        if _xiadan_pids(client):

            time.sleep(3)

            return

        time.sleep(1)

    raise AutoIpoError(

        "XIADAN_LAUNCH_TIMEOUT",

        "F12 后指定 xiadan 未启动",

        "检查同花顺账号是否登录、客户端路径是否正确，查看 runtime_data/errors",

        {"client_id": client.client_id if client else "legacy", "xiadan_path": str(xiadan_path)},

    )





def _login_dialog(client: ClientSpec | None = None):

    """xiadan 进程里含「登录」按钮的 #32770 窗口。优先可见的；隐藏的（换户后不自动显示）restore 后再用。"""

    pids = _xiadan_pids(client)

    hidden = None

    for w in Desktop(backend="win32").windows():

        try:

            if int(w.process_id()) not in pids or w.class_name() != "#32770":

                continue

            if not any(b.window_text() == LOGIN_BTN for b in w.descendants(class_name="Button")):

                continue

            if _row_field(w, "资金帐户", "ComboBox") is None:

                continue

            if w.is_visible():

                return w

            hidden = hidden or w

        except Exception:

            continue

    if hidden is not None:

        try:

            hidden.restore()

            time.sleep(1)

        except Exception:

            pass

        return hidden

    return None





def _main_window(client: ClientSpec | None = None):

    """交易主窗：标题含「网上股票交易系统」的窗口（可能藏在托盘屏外，找到后还原为可见）。"""

    windows = windows_for_pids(

        _xiadan_pids(client), class_prefix="Afx", title_has="网上股票交易系统", visible_only=False

    )

    w = (require_single_window(windows, client.client_id, "xiadan 交易主窗") if client and windows

         else (windows[0] if windows else None))

    if w is not None and not w.is_visible():

        try:

            w.restore()

            time.sleep(1)

        except Exception:

            pass

    return w







def _row_field(dlg, label: str, cls: str):

    """按「静态标签同一行右侧最近的控件」定位输入框（只认可见控件——对话框里堆叠了多套验证方式的隐藏行）。"""

    target = None

    for st in dlg.descendants(class_name="Static"):

        try:

            if not st.is_visible():

                continue

            if st.window_text().replace(" ", "").strip() == label.replace(" ", ""):

                target = st.rectangle()

                break

        except Exception:

            continue

    if target is None:

        return None

    label_cy = (target.top + target.bottom) / 2

    best, best_dx = None, 1e9

    for c in dlg.descendants(class_name=cls):

        try:

            if not c.is_visible():

                continue

            r = c.rectangle()

            if r.width() == 0:

                continue

            cy = (r.top + r.bottom) / 2

            if abs(cy - label_cy) < 15 and r.left >= target.left:

                if r.left - target.left < best_dx:

                    best, best_dx = c, r.left - target.left

        except Exception:

            continue

    return best





def _check_never_show_checkbox(window) -> bool:
    """勾选「30天内不再自动弹出」复选框（防下次登录再弹）；返回是否找到。"""
    for button in window.descendants(class_name="Button"):
        try:
            if "不再自动弹出" not in str(button.window_text() or ""):
                continue
            if button.get_toggle_state() != 1:
                button.click_input()
                time.sleep(0.3)
            return True
        except Exception:
            continue
    return False


def _dismiss_yijiandaxin(window) -> None:
    """一键打新弹窗：先勾「30天内不再自动弹出」再关窗；绝不点申购/确定类按钮。"""
    try:
        _check_never_show_checkbox(window)
        window.close()
        time.sleep(0.5)
    except Exception:
        pass


def _dismiss_popups(client: ClientSpec | None = None) -> None:

    """只关「注册用户提示」类弹窗，绝不动登录对话框。



    该弹窗是顶层 PhonTipWnd（CEF 渲染，枚举不到按钮），只能按相对坐标点「取消」。

    """

    pids = _xiadan_pids(client)

    for w in Desktop(backend="win32").windows():

        try:

            if int(w.process_id()) not in pids or not w.is_visible():

                continue

            if any(b.window_text() == "登录" for b in w.descendants(class_name="Button")):

                continue  # 登录对话框本身跳过

            if "一键打新" in (w.window_text() or ""):
                _dismiss_yijiandaxin(w)
                continue
            if w.class_name() == "PhonTipWnd":

                r = w.rectangle()

                mouse_click(coords=(r.left + int(r.width() * 0.82), r.top + int(r.height() * 0.59)))

                time.sleep(0.5)

                continue

            texts = [s.window_text() for s in w.descendants(class_name="Static")]

            if not any("注册" in t for t in texts):

                continue

            for b in w.descendants(class_name="Button"):

                if b.window_text() == "取消":

                    b.click_input()

                    break

        except Exception:

            continue

















def shot_main_window(name: str, client: ClientSpec | None = None) -> None:

    """实盘留痕：截当前交易主窗存 runtime_data/（AGENTS.md §9 要求），失败不阻塞。"""

    try:

        main = _main_window(client)

        if main is not None:

            out = runtime_path(name)

            out.parent.mkdir(parents=True, exist_ok=True)

            main.capture_as_image().save(str(out))

    except Exception:

        pass





def close_modal_dialogs(client: ClientSpec | None = None) -> int:

    """关掉 xiadan 所有可见模态对话框。只点「取消」或直接关窗——绝不点「确定/确认」，

    避免残留委托确认框被误提交。返回关闭数量。"""

    closed = 0

    pids = _xiadan_pids(client)

    for w in Desktop(backend="win32").windows():

        try:

            if int(w.process_id()) not in pids or not w.is_visible() or w.class_name() != "#32770":

                continue

            if "网上股票交易系统" in (w.window_text() or ""):

                continue

            if "一键打新" in (w.window_text() or ""):
                _dismiss_yijiandaxin(w)
                closed += 1
                continue

            btns = {b.window_text(): b for b in w.descendants(class_name="Button")}

            if "取消" in btns:

                btns["取消"].click_input()

                closed += 1

                time.sleep(0.5)

            elif btns:  # 没有取消键的提示框：直接关窗（等于放弃操作）

                w.close()

                closed += 1

                time.sleep(0.5)

        except Exception:

            continue

    return closed





def _current_fund_account(client: ClientSpec | None = None) -> str:

    """读当前账户的资金账号：主窗里「纯数字且长度≥6」的 ComboBox 文本（切换后它会真实刷新）。"""

    main = _main_window(client)

    if main is None:

        return ""

    for c in main.descendants(class_name="ComboBox"):

        try:

            t = (c.window_text() or "").strip()

            if t.isdigit() and len(t) >= 6:

                return t

        except Exception:

            continue

    return ""





def _account_combo(client: ClientSpec | None = None):

    """顶栏账户下拉（items 含「编辑账户」的那个 ComboBox）。"""

    main = _main_window(client)

    if main is None:

        return None

    for c in main.descendants(class_name="ComboBox"):

        try:

            if "编辑账户" in [i or "" for i in c.item_texts()]:

                return c

        except Exception:

            continue

    return None





def _control_id(control) -> int | None:
    try:
        value = control.control_id()
    except Exception:
        value = getattr(getattr(control, "element_info", None), "control_id", None)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _require_unique_combo(main, key: str):
    settings = ((load_config().get("gui") or {}).get("xiadan") or {})
    if key not in settings:
        raise AutoIpoError(
            "XIADAN_CONTROL_ID_MISSING_CONFIG",
            f"缺少配置 gui.xiadan.{key}",
            "在 config/config.yaml 的 gui.xiadan 下配置稳定控件 ID；禁止猜测控件",
            {"key": key},
        )
    try:
        wanted = int(settings[key])
    except (TypeError, ValueError):
        raise AutoIpoError(
            "XIADAN_CONTROL_ID_INVALID", f"gui.xiadan.{key} 必须是整数",
            "修正配置后运行 python run.py doctor",
            {"key": key, "value": settings[key]},
        ) from None
    matches = [c for c in main.descendants() if _control_id(c) == wanted]
    if len(matches) != 1:
        raise AutoIpoError(
            "XIADAN_CONTROL_NOT_UNIQUE",
            f"gui.xiadan.{key}={wanted} 命中 {len(matches)} 个控件",
            "核对控件 ID 与当前 xiadan 版本；禁止猜测控件",
            {"key": key, "control_id": wanted, "count": len(matches)},
        )
    return matches[0]


def _account_item_matches(item_text: str, fund_account: str, display_name: str = "") -> bool:
    """下拉行同时命中资金账号与显示名（如有）才认定是目标账户行。"""
    text = str(item_text or "").replace(" ", "")
    digits = "".join(ch for ch in text if ch.isdigit())
    if fund_account and fund_account not in digits:
        return False
    if display_name and display_name.replace(" ", "") not in text:
        return False
    return bool(fund_account or display_name)


def runtime_fund_account_hash(client: ClientSpec | None = None) -> str:
    """读 xiadan 当前资金账号并返回哈希；读不到返回空串（调用方回退配置哈希）。"""
    try:
        full = _current_fund_account(client)
    except Exception:
        return ""
    if not full:
        return ""
    return hash_fund_account(mask_fund_account(full).replace(" ", ""))

def _open_dropdown_and_click_row(combo, row_idx: int, total_rows: int,

                                 client: ClientSpec | None = None) -> None:

    """点开账户下拉并点击指定行（必须真实点击行——select() 只改显示文字不换账户上下文）。



    真实鼠标点击要求窗口在屏幕前台；弹层未开则按 ESC 重置后重试，最多 3 次。

    """

    main = _main_window(client)

    if main is not None:

        try:

            main.restore()

            main.set_focus()

            time.sleep(0.8)

        except Exception:

            pass

    settings = (load_config().get("gui") or {}).get("hexin_login") or {}

    attempts = int(settings.get("dropdown_attempts", 5))

    popup_wait_s = float(settings.get("dropdown_wait_s", 2))

    r = combo.rectangle()

    popup = None

    for _try in range(attempts):

        try:

            combo.type_keys("{ESC}")

        except Exception:

            pass

        points = [(r.right - 12, (r.top + r.bottom) // 2),

                  (r.right - 5, (r.top + r.bottom) // 2),

                  ((r.left + r.right) // 2, (r.top + r.bottom) // 2)]

        mouse_click(coords=points[_try % len(points)])

        deadline = time.time() + popup_wait_s

        while time.time() < deadline:

            for w in Desktop(backend="win32").windows():

                try:

                    if w.class_name() == "ComboLBox" and w.is_visible():

                        popup = w

                        break

                except Exception:

                    continue

            if popup is not None:

                break

            time.sleep(0.2)

        if popup is not None:

            break

        if main is not None:

            try:

                main.set_focus()

                time.sleep(0.3)

            except Exception:

                pass

    if popup is None:

        raise RuntimeError("账户下拉弹层未打开")

    pr = popup.rectangle()

    row_h = pr.height() / total_rows

    mouse_click(coords=(pr.left + pr.width() // 2, int(pr.top + row_h * (row_idx + 0.5))))





def _switch_to_account(fund_account: str, timeout: int = 90,

                       client: ClientSpec | None = None) -> None:

    """逐行试点账户下拉，直到主窗资金账号变成目标值。映射关系缓存到 account_map.json。"""

    deadline = time.time() + timeout

    while time.time() < deadline:

        combo = _account_combo(client)

        if combo is None:

            time.sleep(2)

            continue

        all_items = [i for i in combo.item_texts() if i]

        items = [i for i in all_items if "编辑" not in i]

        # 缓存的映射优先试

        cached = get_cached_display_name(fund_account, _client_id(client))

        ordered = ([cached] + [i for i in items if i != cached]) if cached in items else items

        last_popup_error = None

        for item in ordered:

            prev = _current_fund_account(client)

            try:

                _open_dropdown_and_click_row(combo, all_items.index(item), len(all_items), client)

            except Exception as exc:

                last_popup_error = exc

                combo = _account_combo(client) or combo

                time.sleep(1)

                continue

            # 等资金账号刷新：先等它离开旧值，再判断是否命中目标

            sub_deadline = time.time() + 12

            while time.time() < sub_deadline:

                cur = _current_fund_account(client)

                if cur == fund_account:

                    save_account_cache_entry(fund_account, item, client_id=_client_id(client))

                    return

                if cur and prev and cur != prev:

                    break  # 已切到别的账户，试下一行

                time.sleep(1)

            combo = _account_combo(client) or combo

            all_items = [i for i in combo.item_texts() if i] or all_items

        if last_popup_error:

            raise RuntimeError(f"账户下拉弹层未打开：{str(last_popup_error)[:80]}")

        if last_popup_error:
            raise RuntimeError(f"账户下拉弹层未打开：{str(last_popup_error)[:80]}")
        raise RuntimeError("目标账户不在客户端已登录列表中，请先在客户端登录该账户")  # 不带资金账号：异常会进推送正文

    raise RuntimeError("切换账户超时")





def logged_in_labels(client: ClientSpec | None = None) -> list[str]:

    """xiadan 顶栏账户下拉当前全部账户显示名（只读；boot_login/hexin_login 用作登录完成判据）。"""

    combo = _account_combo(client)

    if combo is None:

        return []

    try:

        return [i for i in combo.item_texts() if i and "编辑" not in i]

    except Exception:

        return []





def ensure_logged_in(account_id: str, timeout: int = 120, client: ClientSpec | None = None) -> str:

    """把 xiadan 切换到指定账户（顶栏下拉点行切换），失败抛异常。



    前提：该账户已在客户端登录过且保持在已登录账户列表里（xiadan 需经 hexin F12 带令牌启动）。

    返回客户端显示的账户名（形如「平安证券-张*龙」），调用方用它做推送/日志的账户标识。

    """

    cfg = load_config()

    secrets = load_secrets()

    if client is None:

        from execution.client_registry import load_client_spec

        specs = [load_client_spec(cfg)]

        if len(specs) != 1:

            raise AutoIpoError(

                "CLIENT_CONTEXT_REQUIRED",

                "多客户端运行必须显式指定 client_id",

                "调用 run.py --client ths1|ths2|all 或传入 ClientSpec",

            )

        client = specs[0]

    accounts = {a["id"]: a for a in cfg.get("accounts", [])}

    if account_id not in accounts:

        raise RuntimeError(f"config 中不存在账户 {account_id}")

    cred = (secrets.get("accounts_secrets") or {}).get(account_id) or {}

    fund_account = cred.get("fund_account")

    if not fund_account:

        raise RuntimeError(f"账户 {account_id} 未在管理界面填写资金账号")



    _launch_xiadan_via_f12(str(client.xiadan_path), client=client)

    deadline = time.time() + timeout

    while time.time() < deadline:

        _dismiss_popups(client)

        if _main_window(client) is not None:

            break

        time.sleep(2)

    else:

        raise RuntimeError("等待交易主窗超时（客户端可能未登录任何账户）")



    from execution.hexin_login import detect_manual_dialogs

    dialogs = detect_manual_dialogs(client)

    if dialogs:

        raise RuntimeError("人工处理：客户端弹出密码/验证码登录框（" + "；".join(dialogs) + "）")



    if _current_fund_account(client) != fund_account:

        _switch_to_account(fund_account, client=client)

    # 账户名优先用缓存里「验证过的客户端显示名」——资金账号已吻合时不会触发切换，

    # 此时下拉框显示文字可能是历史残留（显示≠上下文），不可信

    cached = get_cached_display_name(fund_account, _client_id(client))

    if cached:

        return cached

    combo = _account_combo(client)

    return (combo.window_text() or account_id) if combo else account_id





def fund_account_hash_for(account_id: str) -> str:

    cred = (load_secrets().get("accounts_secrets") or {}).get(account_id) or {}

    fund_account = cred.get("fund_account")

    if not fund_account:

        raise RuntimeError(f"账户 {account_id} 未填写资金账号")

    return hash_fund_account(str(fund_account))





def account_session_state(account_id: str, display_name: str = "",

                          client: ClientSpec | None = None) -> AccountSessionResult:

    """只读获取当前 xiadan 账户会话；输出只含哈希/脱敏资金账号。"""

    expected_hash = fund_account_hash_for(account_id)

    labels = logged_in_labels() if client is None else logged_in_labels(client)

    matched = next((label for label in labels if account_id in label or

                    (display_name and display_name in label)), "")

    current_raw = _current_fund_account() if client is None else _current_fund_account(client)

    current_hash = hash_fund_account(current_raw) if current_raw else ""

    present = bool(matched or current_hash == expected_hash)

    if not present:

        status = STATUS_NOT_LOGGED_IN

    elif current_hash == expected_hash:

        status = STATUS_READY

    elif current_raw:

        status = STATUS_WRONG_ACCOUNT

    else:

        status = STATUS_NOT_LOGGED_IN

    return AccountSessionResult(

        account_id=account_id,

        display_name=matched or display_name,

        fund_account_hash=expected_hash,

        main_menu_row=get_cached_menu_row(current_raw, _client_id(client)) if current_raw else None,

        xiadan_present=present,

        current_fund_account=mask_fund_account(current_raw),

        status=status,

        client_id=_client_id(client),

    )





def ensure_account_session(account_id: str, timeout: int = 120,

                           client: ClientSpec | None = None) -> AccountSessionResult:

    """切换并验证账户会话。只读查询，不触发任何委托。"""

    try:

        display_name = ensure_logged_in(account_id, timeout=timeout, client=client)

        return account_session_state(account_id, display_name=display_name, client=client)

    except Exception as exc:

        text = str(exc)

        status = STATUS_XIADAN_FAILED

        if any(word in text for word in ("人工处理", "验证码", "交易密码", "密码/验证码")):

            status = STATUS_DIALOG_REQUIRED

        elif "不在客户端已登录列表" in text:

            status = STATUS_NOT_LOGGED_IN

        elif "资金账号" in text or "实际登录" in text:

            status = STATUS_WRONG_ACCOUNT

        return AccountSessionResult(

            account_id=account_id,

            status=status,

            error=text[:100],

            client_id=_client_id(client),

        )





def ensure_xiadan_ready(timeout: int = 40, client: ClientSpec | None = None) -> None:

    """确保 F12 带令牌的 xiadan 会话载体已启动；只启动/恢复，不下单。"""

    cfg = load_config()

    if client is None:

        from execution.client_registry import load_client_spec

        specs = [load_client_spec(cfg)]

        if len(specs) != 1:

            raise AutoIpoError(

                "CLIENT_CONTEXT_REQUIRED",

                "多客户端运行必须显式指定 client_id",

                "调用 run.py --client ths1|ths2|all 或传入 ClientSpec",

            )

        client = specs[0]

    _launch_xiadan_via_f12(str(client.xiadan_path), timeout=timeout, client=client)

    deadline = time.time() + timeout

    while time.time() < deadline:

        _dismiss_popups(client)

        if _main_window(client) is not None:

            return

        time.sleep(2)

    raise RuntimeError("等待交易主窗超时（xiadan 会话载体未就绪）")


