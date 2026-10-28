# Mission Plan

## 步骤
1. 登录账户分类与登录弹窗处理。
   验证：模拟需登录账户、10 户上限、关闭弹窗后继续、点错账户不计成功。
2. 客户端按任务启动/关闭与运行状态记录。
   验证：只关闭受管进程；关闭失败有错误码；重复任务幂等。
3. 开机联网错过后补。
   验证：日历/申购/中签分别测试已过期、窗口内、已完成和重试场景。
4. 三类标准化回执模板与脱敏。
   验证：标题、正文、空结果、失败结果和无敏感字段测试。
5. 全量回归。
   验证：`python -m pytest -q`、64/32 位 compileall、`python run.py doctor`、dry-run 零真实委托。

## 验证结果
- `python -m pytest -q`：131 passed。
- `.venv32\Scripts\python.exe -c "import pywinauto, win32gui, jqktrader; print('32bit ok')"`：32bit ok。
- 64/32 位 `compileall`：通过。
- `scheduler/register_tasks.ps1`、`scheduler/setup.ps1` PowerShell 语法解析：通过。
- `python run.py doctor`：`ok=true`，14 个账户配置、11/11 启用账户密钥元数据、双客户端路径、DPAPI 均通过。
- `python run.py subscribe --day 2026-10-17`：dry-run 正常，结果文件无 `submitted`，零真实委托。

## 结果
- 可直接登录账户动态识别；需资金账号/密码/验证码账户不点。
- “委托下单”登录框关闭后继续；其他人工安全弹窗停止并报告。
- GUI 任务前启动、任务后温和关闭；双客户端全周期严格串行。
- 开机联网后补当日任务；申购过期跳过；中签未定继续补查。
- 登录/申购/中签标准回执已接入，敏感字段脱敏。
- 回执重试可展开嵌套申购明细；中签回执保留结构化账户/标的/数量/缴款字段。

## 风险与遗留
- 同花顺 UI 升级可能改变菜单和弹窗控件，需要结构化诊断与截图兜底。
- 关闭用户已打开的客户端可能影响人工操作；生命周期必须记录 `preexisting` 并优先温和关闭。
- 中签数据未公布时应重试，不得把“暂无数据”当最终无中签。
- 当前为非交易时段，真实交易日仍需按 discover → boot-login → preflight → dry-run → 人工确认 → 单次 live 验收。
- THS2 需密码/验证码账户只跳过和留痕，不自动填写、不识别验证码。
