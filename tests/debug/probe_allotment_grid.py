# AI-SUMMARY: 现场探针——中签明细网格/剪贴板读取诊断（一次性调试脚本）
import json
import sys
import time

sys.path.insert(0, r"C:\Users\93724\Desktop\自动打新")

from shared.config import load_config
from execution.client_registry import ClientSpec
from execution.ths_account_config import load_ths_account_mode, read_ths_password
from execution.ths_account_runner import GentleClientLifecycle
from execution.ths_account_ui import ThsAccountUI
from execution.ths_account_switch import ThsLoginAccount, switch_ths_account
from execution.ths_client import connect, _find_ctrl, _default_focus

out = {}
cfg = load_config()
mode = load_ths_account_mode(cfg)
accounts = [a for a in mode.accounts if a.enabled]
client = ClientSpec(client_id="ths_account_switch", hexin_path=mode.hexin_path, xiadan_path=mode.xiadan_path)

lifecycle = GentleClientLifecycle(client, cfg)
lifecycle.start()
try:
    ui = ThsAccountUI(client, cfg, known_ths_accounts=[a.username for a in accounts])
    target = ThsLoginAccount(username=accounts[0].username)
    res = switch_ths_account(target, client, lambda: read_ths_password(accounts[0].username), ui, 120)
    out["switch"] = res.status

    refs = ui.discover_fund_accounts()
    out["refs"] = [r.display_masked for r in refs]
    first = next(r for r in refs if r.row_kind == "direct")
    login_res = ui.login_fund_account(first)
    out["fund_login"] = getattr(login_res, "status", str(login_res))

    user = connect(client=client)
    out["xiadan_main_title"] = user._main.window_text()
    user._switch_left_menus(["新股申购", "查询中签明细"])
    time.sleep(2)
    grid = _find_ctrl(user._main, 1047, "CVirtualGridCtrl")
    out["grid_rect"] = str(grid.rectangle())
    out["grid_visible"] = bool(grid.is_visible())
    _default_focus(user._main)
    time.sleep(0.5)
    import win32gui
    out["foreground_title"] = win32gui.GetWindowText(win32gui.GetForegroundWindow())
    grid.type_keys("^A^C", set_foreground=False)
    time.sleep(0.5)
    import pywinauto.clipboard
    content = pywinauto.clipboard.GetData()
    out["clipboard_head"] = content[:300]
    out["clipboard_len"] = len(content)
finally:
    lifecycle.close()
print(json.dumps(out, ensure_ascii=False, indent=2))
