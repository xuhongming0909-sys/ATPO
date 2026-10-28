# AI-SUMMARY: 同花顺下单客户端连接封装（jqktrader）——按 ClientSpec.xiadan_path 连接指定实例
from execution.client_registry import ClientSpec
from shared.config import load_config
from shared.errors import AutoIpoError


def _ctrl_visible(ctrl) -> bool:
    """控件全链可见性：IsWindowVisible 自带祖先链判定（任一上级面板隐藏即为 False）。
    pywinauto is_visible 只看自身样式位，对面板堆叠场景会误判，故不用。"""
    import win32gui
    try:
        return bool(win32gui.IsWindowVisible(ctrl.handle))
    except Exception:
        return False


def _find_ctrl(main, control_id: int, class_name: str):
    """在窗口里按 control_id + 类名找控件（xiadan 堆叠多套同 ID 控件）。
    优先取全链可见的候选，都没有才退回第一个（调用方需能容忍后续可见性校验失败）。"""
    cands = []
    for d in main.descendants(class_name=class_name):
        if _safe_ctrl_id(d) == control_id:
            cands.append(d)
    if not cands:
        raise RuntimeError(f"控件未找到: {class_name} #{control_id}")
    for c in cands:
        if _ctrl_visible(c):
            return c
    return cands[0]


def _safe_ctrl_id(ctrl) -> int:
    try:
        return ctrl.control_id()
    except Exception:
        return -1


def _patch_jqktrader(user) -> None:
    """xiadan 窗口按底栏页签堆叠多套同 control_id 的控件，jqktrader 原生 child_window
    唯一匹配假设会失败；逐处替换为 descendants + 面板可见优先的查找。"""
    def _get_left_tree():
        return _find_ctrl(user._main, 129, "SysTreeView32")

    def _get_balance_from_statics():
        # 余额面板按账户堆叠缓存：只有当前账户的面板可见（需先导航到资金股票页）
        result = {}
        for key, cid in user._config.BALANCE_CONTROL_ID_GROUP.items():
            cands = []
            for d in user._main.descendants(class_name="Static"):
                try:
                    if d.control_id() == cid:
                        cands.append(d)
                except Exception:
                    continue
            chosen = None
            for c in cands:
                if _ctrl_visible(c):
                    chosen = c
                    break
            if chosen is None and cands:
                chosen = cands[0]
            text = chosen.window_text() if chosen is not None else ""
            try:
                result[key] = float(text)
            except (TypeError, ValueError):
                result[key] = 0.0
        return result

    user._get_left_menus_handle = _get_left_tree
    user._get_balance_from_statics = _get_balance_from_statics

    def _switch_left_menus(path, sleep=0.2):
        """点左侧菜单树。两遍策略：先只试点面板可见的树（消息选中隐藏树不会真翻页），
        都不行再全量试（兼容券商定制面板——同名节点子项不同的树可能都在隐藏面板上）。"""
        import time as _t
        trees = [d for d in user._main.descendants(class_name="SysTreeView32")
                 if _safe_ctrl_id(d) == 129]
        trees.sort(key=lambda t: not _ctrl_visible(t))  # 全链可见的树优先
        last = None
        for d in trees:
            try:
                d.get_item(path).select()
                _t.sleep(sleep)
                return
            except Exception as e:
                last = e
                continue
        raise RuntimeError(f"左侧菜单路径 {path} 未找到: {str(last)[:80]}")

    user._switch_left_menus = _switch_left_menus

    def _type_edit_control_keys(control_id, text):
        # 买入表单输入框同样有多套堆叠，必须点可见面板那个
        editor = _find_ctrl(user._main, control_id, "Edit")
        # 2026-10-27：jqktrader 按代码前缀舍入（深市 3 位），可转债 100.0 变 100.001，
        # 触发「小数部分应为2位」确认弹窗卡死流程。价格框统一规整：整数去尾、最多 2 位小数。
        try:
            if int(control_id) == int(user._config.TRADE_PRICE_CONTROL_ID):
                value = float(text)
                text = str(int(value)) if value == int(value) else f"{value:.2f}".rstrip("0").rstrip(".")
        except Exception:
            pass
        if getattr(user, "_editor_need_type_keys", False):
            editor.select()
            editor.type_keys(text)
        else:
            editor.set_edit_text(text)

    def _dismiss_price_format_dialog() -> bool:
        """「委托价格的小数部分应为2位，是否继续?」→ 点「否」放弃本单（绝不点是）。

        2026-10-27 实战：该弹窗阻塞 F8 核验并级联拖慢后续所有账户。
        """
        import win32gui
        import win32process

        dismissed = False

        def on_window(hwnd, _):
            nonlocal dismissed
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if not win32gui.IsWindowVisible(hwnd):
                    return
                texts = []
                children = []
                win32gui.EnumChildWindows(hwnd, lambda h, _: children.append(h), None)
                no_btn = None
                for h in children:
                    try:
                        cls = win32gui.GetClassName(h)
                        t = win32gui.GetWindowText(h)
                        if t:
                            texts.append(t)
                        if cls == "Button" and t == "否(N)":
                            no_btn = h
                    except Exception:
                        continue
                if no_btn is None and any("小数部分" in t for t in texts):
                    for h in children:
                        try:
                            if win32gui.GetClassName(h) == "Button" and win32gui.GetWindowText(h).startswith("否"):
                                no_btn = h
                                break
                        except Exception:
                            continue
                if no_btn is not None and any("小数部分" in t for t in texts):
                    import win32api
                    import win32con
                    rect = win32gui.GetWindowRect(no_btn)
                    win32api.SetCursorPos(((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2))
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                    dismissed = True
            except Exception:
                pass

        try:
            win32gui.EnumWindows(on_window, None)
        except Exception:
            pass
        return dismissed

    user._dismiss_price_format_dialog = _dismiss_price_format_dialog

    def _submit_trade():
        import time as _t
        _t.sleep(0.2)
        _find_ctrl(user._main, user._config.TRADE_SUBMIT_CONTROL_ID, "Button").click()

    user._type_edit_control_keys = _type_edit_control_keys
    user._submit_trade = _submit_trade

    # 2026-10-28：科创板/沪市申购代码（5/6/7/11 开头）在 jqktrader 里不设板块，
    # 走单笔兜底会因板块缺失失败。buy 前显式补设上海Ａ股/深圳Ａ股。
    _raw_buy = user.buy

    def _buy_with_exchange(security, price, amount, **kwargs):
        code = str(security or "")[-6:]
        try:
            if code and code[0] in "567":
                user._set_stock_exchange_type("上海Ａ股")
            elif code and code[0] in "023":
                user._set_stock_exchange_type("深圳Ａ股")
        except Exception:
            pass
        return _raw_buy(security, price, amount, **kwargs)

    user.buy = _buy_with_exchange
    # 网格控件同样有多套堆叠（CVirtualGridCtrl），剪贴板策略的取控件环节换掉。
    # 面板隐藏时控件样式位不可见会触发 type_keys 的 verify_visible 误伤——中和它。
    strat = user.grid_strategy_instance

    def _get_grid_patched(cid):
        grid = _find_ctrl(user._main, cid, "CVirtualGridCtrl")
        try:
            grid.verify_visible = lambda *a, **k: None
        except Exception:
            pass
        return grid

    strat._get_grid = _get_grid_patched

    def _get_via_message(cid):
        # 改用 WM_COMMAND 网格复制命令（0xE122），不依赖键盘焦点/前台窗口
        import time as _t

        import pywinauto.clipboard

        grid = _get_grid_patched(cid)
        grid.post_message(0x0111, 0xE122, 0)
        _t.sleep(0.3)
        content = pywinauto.clipboard.GetData()
        return strat._format_grid_data(content)

    strat.get = _get_via_message


def _default_focus(main) -> None:
    """置前 xiadan 主窗：恢复最小化 + set_focus；失败静默（由内容校验兜底）。"""
    try:
        import win32gui

        handle = int(getattr(main, "handle", 0) or 0)
        if handle:
            win32gui.ShowWindow(handle, 9)
    except Exception:
        pass
    try:
        main.set_focus()
    except Exception:
        pass


def read_grid_checked(user, control_id: int, known_keys, *, attempts: int = 3,
                      focus_fn=None, sleep_fn=None) -> list[dict]:
    """置前主窗后读网格；行内无已知列键（焦点错窗/剪贴板串扰）时重读，有界。"""
    import time

    focus = focus_fn or _default_focus
    sleep = sleep_fn or time.sleep
    rows: list[dict] = []
    for attempt in range(max(1, int(attempts))):
        focus(user._main)
        rows = user._get_grid_data(control_id) or []
        if not rows or all(any(k in row for k in known_keys) for row in rows):
            break
        if attempt + 1 < max(1, int(attempts)):
            sleep(1.0)
    return rows


def read_grid_via_ocr(user, control_id: int, header_keys=None, *, attempts: int = 3,
                      sleep_fn=None) -> list[dict] | None:
    """截取网格区域做屏幕 OCR；读像素不碰剪贴板，不触发 THS 拷贝验证码。
    None=未读到表头（读取失败）；[]=页面正常但无数据。"""
    import time
    import uuid

    from PIL import ImageGrab

    from shared.paths import runtime_path
    from shared.username_ocr import read_grid_with_ocr

    sleep = sleep_fn or time.sleep
    for attempt in range(max(1, int(attempts))):
        _default_focus(user._main)
        grid = _find_ctrl(user._main, control_id, "CVirtualGridCtrl")
        rect = grid.rectangle()
        box = (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
        path = runtime_path("ocr", f"grid_{uuid.uuid4().hex}.png")
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            ImageGrab.grab(bbox=box).save(path)
            rows = read_grid_with_ocr(path, header_keys=header_keys)
            if rows:
                for row in rows:
                    if "_top" in row:
                        row["_top"] = float(row["_top"]) + box[1]
                        row["_bottom"] = float(row["_bottom"]) + box[1]
        finally:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
        if rows is not None:
            return rows
        if attempt + 1 < max(1, int(attempts)):
            sleep(1.0)
    return None

TODAY_ENTRUST_MENU_PATH = ["查询[F4]", "当日委托"]
TODAY_ENTRUST_GRID_CTRL = 1047
TODAY_ENTRUST_KEYS = ("证券代码", "证券名称", "委托编号", "合同编号", "委托时间", "委托数量", "委托状态")


def read_today_entrusts_via_ocr(user, attempts: int = 2, interval_s: float = 0.2):
    """读取 F8 当日委托；只截屏 OCR，不触发 THS 网格复制验证码。"""
    import time

    user._switch_left_menus(TODAY_ENTRUST_MENU_PATH)
    for attempt in range(max(1, int(attempts))):
        rows = read_grid_via_ocr(user, TODAY_ENTRUST_GRID_CTRL, TODAY_ENTRUST_KEYS)
        if rows is not None:
            return rows
        if attempt + 1 < max(1, int(attempts)):
            time.sleep(interval_s)
    return None


def connect(retries: int = 15, interval: float = 2.0, client: ClientSpec | None = None):
    """连接已登录的 xiadan.exe。

    jqktrader connect 可能杀旧进程重启新实例，新窗口出现有延迟（自动登录也要几秒），
    因此对「No windows for that process」做有限重试。
    """
    import time

    import jqktrader

    if client is None:
        from execution.client_registry import load_client_spec
        client = load_client_spec(load_config())
    kwargs = {"exe_path": str(client.xiadan_path)}
    user = jqktrader.use()
    last_err = None
    for _ in range(retries):
        try:
            user.connect(**kwargs)
            _patch_jqktrader(user)
            return user
        except RuntimeError as e:
            if "No windows" not in str(e):
                raise
            last_err = e
            time.sleep(interval)
    raise last_err
