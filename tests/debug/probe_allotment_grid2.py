# AI-SUMMARY: 探针 2——点击网格物理聚焦后再 ^A^C，验证剪贴板是否更新
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
    switch_ths_account(target, client, lambda: read_ths_password(accounts[0].username), ui, 120)
    refs = ui.discover_fund_accounts()
    first = next(r for r in refs if r.row_kind == "direct")
    ui.login_fund_account(first)

    user = connect(client=client)
    user._switch_left_menus(["新股申购", "查询中签明细"])
    time.sleep(2)
    grid = _find_ctrl(user._main, 1047, "CVirtualGridCtrl")
    _default_focus(user._main)
    time.sleep(0.3)
    grid.click_input()
    time.sleep(0.5)
    grid.type_keys("^A^C", set_foreground=False)
    time.sleep(0.5)
    import pywinauto.clipboard
    content = pywinauto.clipboard.GetData()
    out["clipboard_head"] = content[:300]
    out["clipboard_len"] = len(content)
    import win32gui
    out["foreground_title"] = win32gui.GetWindowText(win32gui.GetForegroundWindow())
finally:
    lifecycle.close()
print(json.dumps(out, ensure_ascii=False, indent=2))
