# AI-SUMMARY: 中签明细读取——xiadan「新股申购→查询中签明细」网格数据（切户模式由 ths_account_runner 逐资金账户调用）
MENU_PATH = ["新股申购", "查询中签明细"]
GRID_CTRL = 1047


_KNOWN_KEYS = ("证券代码", "证券名称", "apply_code", "name", "中签数量", "中签日期")


def query_allotment(user) -> list[dict]:
    """读「查询中签明细」网格；行不含任何已知列键视为误读（如焦点错窗），拒绝放行。"""
    from execution.ths_client import read_grid_via_ocr

    user._switch_left_menus(MENU_PATH)
    rows = read_grid_via_ocr(user, GRID_CTRL, _KNOWN_KEYS)
    if rows is None:
        raise RuntimeError("中签明细网格读取失败（未识别到表头）")
    return rows
