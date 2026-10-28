# Mission Spec — ths-cycle 真实失败修复（username 解析 / 温和关闭 / 弹窗分类）

- 任务类型：bugfix（TDD）
- 目标：`python run.py ths-cycle --date 2026-10-17 --phase login` 链路不再出现
  THS_CURRENT_ACCOUNT_UNREADABLE、`win32gui.GetWindowThreadProcessId` 缺失、close `timed out`；
  真实测试后 hexin.exe/xiadan.exe 无残留。
- 范围：仅 `execution/ths_account_ui.py`、`execution/client_lifecycle.py`、
  `execution/ths_account_switch.py` 及对应 tests；debug 探查脚本放 `tests/debug/`。

## 问题与验收

1. WM_CLOSE 失败：`win32gui.GetWindowThreadProcessId` 不存在。
   验收：改用 `win32process.GetWindowThreadProcessId`；mock 复现后通过；WM_CLOSE 只发给精确 PID 窗口。
2. 当前 THS username 读不出（真实主窗标题 `同花顺(9.60.71) - 自选股`）。
   验收：按 控件可见文本 → 通用可见文本 → 进程命令行（仅匹配已知 username）三级解析；
   命令行原文/敏感哈希绝不进入返回值、异常、日志。
3. close `timed out`。
   验收：close_main_window 只发 WM_CLOSE 不等待销毁；close_ths_client 等待并精确点击
   “切换账号/退出”弹窗按钮，随后验证进程退出；全程不强杀。
4. 弹窗分类按窗口结构：标题“委托下单”+ 资金账号/交易密码/验证码 特征 = 资金账户登录弹窗，
   立即关闭并继续下一可直登账户（dialog_required/dialog_closed，manual_required=False）。
   只有非该登录窗的安全验证/人工弹窗才 manual_required 阻断。
   验收：更新 tests/test_ths_account_ui.py 相反断言；结构判定不只看“验证码”词。

## 约束

- TDD mock；真实仅只读控件/命令行探查（命令行不打印原文），不下单、不推送。
- 不强杀；不改 execution/ 之外的生产代码；配置不新增键。
- 真实验证结束 hexin.exe/xiadan.exe 必须已温和关闭、无残留。

## 对正式 spec 影响

无冲突：`specs/ths-account-switch.md` 已规定“资金账号/交易密码/验证码登录框先关再继续”，
本次是代码与测试对齐既有规格，不改正式 spec。