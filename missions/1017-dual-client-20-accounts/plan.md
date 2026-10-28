# Mission Plan

## 目标
把单同花顺实例的动态账户链路扩展为“双实例串行、每实例最多 10 户、账户动态识别、全局防重复”，最终覆盖新股与可转债申购及中签查询。

## 实施基线

- 单实例动态账户链路已有 76 项测试；双实例改造开始前 32 位依赖导入通过。
- 本机配置已注册 ths1/ths2 两个精确 exe 路径，账户不绑定 client_id 或 menu_row。
- 本计划创建时是周末：不执行真实委托；券商不可用只记录当前状态。
## 可行方案

### 0. 只读盘点（先做，零委托）
1. 校验两个安装目录、`hexin.exe`/`xiadan.exe` 路径和独立配置目录。
2. 分别枚举 THS1、THS2 的进程、主窗、hexin 账户菜单文本、xiadan 账户下拉文本。
3. 输出脱敏清单：客户端、显示名、资金账号哈希、是否匹配 config、是否重复。
4. 校验每客户端最多 10 户；检查 THS2 是否仍继承 THS1 登录态。
5. 只读输出存 `runtime_data/client_discovery/`，完整账号不落盘。

验证：两个客户端各有独立进程/窗口；输出中无完整资金账号；未匹配/重复账户被明确列出。

### 1. 先改正式需求与配置模型
1. 更新 `specs/spec.md`、`specs/execution.md`、`INDEX.md`。
2. 配置改为客户端注册表，账户仍保持扁平动态元数据：

```yaml
execution:
  mode: live
  clients:
    ths1:
      enabled: true
      hexin_path: 'E:\同花顺\同花顺\hexin.exe'
      xiadan_path: 'E:\同花顺\同花顺\xiadan.exe'
    ths2:
      enabled: true
      hexin_path: 'E:\同花顺2\同花顺\hexin.exe'
      xiadan_path: 'E:\同花顺2\同花顺\xiadan.exe'
  client_order: [ths1, ths2]
```

3. `accounts[]` 不写死 `client`、券商白名单或行号；权限和资金账号仍是账户元数据/秘密配置。
4. 新账户接入只需改 config/secrets，不改代码；客户端里换成另一组已配置账户也无需改代码。
5. 保留 `gui.hexin_login` 集中参数；两个克隆实例默认共用同一 GUI 参数。

验证：配置回显、路径存在、账号不进入代码；旧的单 `xiadan_path` 依赖全部迁移。

### 2. 客户端隔离（最关键）
新增统一 `ClientContext`：
`client_id / hexin_path / xiadan_path / hexin_pids / xiadan_pids / hexin_window / xiadan_window / current_account`。

改造原则：
- 进程和窗口查找只在指定客户端的 PID/路径范围内进行。
- F12 只发送到该客户端的 hexin 主窗。
- `ths_client.connect()` 只连接该客户端的 `xiadan_path`。
- `logged_in_labels()`、`ensure_logged_in()`、`ensure_account_session()`、截图、弹窗清理全部带客户端上下文。
- 任一客户端的窗口归属不唯一即报错，不选“第一个窗口”。
- 两个客户端只允许串行执行；增加全局 GUI 操作锁，防止计划任务重叠时互相抢焦点。

验证：模拟两个 PID/窗口集合；THS1 操作永远不影响 THS2；错误窗口命中测试必须失败。

### 3. 动态多账户选择
1. 对每个客户端分别读取 hexin 菜单文本和 xiadan 下拉文本。
2. 用 `execution/account_scope.py` 按显示名/稳定别名匹配 config，不按 `menu_row`。
3. 记录 `main_menu_row` 只作缓存/诊断；行号变化、账户重排后必须重新匹配。
4. 每客户端最多选当前实际列表 10 户。
5. 未匹配、歧义、未配置账户只报告 `config_missing` / `ambiguous`，不执行。
6. 同一资金账号哈希跨客户端出现时，只允许一个客户端执行，第二处记 `duplicate_account`。

验证：账户顺序改变仍能匹配；错误行点击必须标 `wrong_account`；换一组已配置账户无需代码修改。

### 4. 串行 Boot Login
流程：

```text
网络就绪
  → THS1 启动/恢复
  → THS1 账户菜单逐户“下拉→点户→重新下拉”
  → THS1 F12 → THS1 xiadan 账户列表/资金账号逐户复核
  → THS2 启动/恢复
  → THS2 同样逐户登录
  → THS2 F12 → THS2 xiadan 复核
  → 汇总 20 户或当前可登录账户状态
```

- 单户失败不阻塞同客户端其他账户。
- 同客户端出现密码/验证码弹窗时停止该客户端剩余登录；另一个客户端可继续，但整体结果必须报阻塞。
- 每客户端独立截图、日志、结果 JSON。
- 本阶段只登录和切换，不下单。

验证：交易日重复运行幂等；已登录账户不重复登录；THS2 不能误操作 THS1。

### 5. 串行 Preflight / Subscribe / Allotment
- `run.py` 新增 `--client ths1|ths2|all`，默认 `all` 且按 `client_order` 串行。
- Preflight 分客户端输出环境、网络、日历、路径、动态账户、会话哈希和重复账户检查。
- Subscribe：THS1 全部账户完成后才进入 THS2；每户 `ensure_logged_in` → `connect(client)` → 批量新股/买入表单兜底 → F8 核验。
- Allotment：同样按客户端串行读取「查询中签明细」。
- 订单台账改为全局稳定账户键（优先 `fund_account_hash`，无哈希时用 config account key），另存 `client_id`；同账户跨客户端不能重复提交。
- 保留现有安全闸门：`execution.mode=live` + `--live`、申购时段、每账户+代码+日期一次、`unknown/submitted_unverified` 禁止重试、live 操作留痕截图。

验证：模拟两客户端、20 户、部分失败、重复账户、断点重跑；测试不得连接真实客户端。

### 6. 测试与真实验收
单元测试（全部 mock）：
- 两个独立进程/窗口不能串线。
- F12 和 jqktrader 只绑定目标客户端。
- 账户顺序变化、菜单行缓存错误、点错行。
- 一个客户端弹窗停止，另一个客户端继续。
- 主界面成功但 xiadan 列表缺失。
- 跨客户端同资金账号哈希防重复。
- 运行两次结果一致。

真实验收顺序：
1. `python -m pytest -q`。
2. `.venv32\Scripts\python.exe -c "import pywinauto, win32gui, jqktrader; print('ok')"`。
3. 只读 discovery：THS1 + THS2 各自列表、匹配数、重复哈希。
4. 交易日 `boot-login --client all`：目标是 20/20 ready；周末/券商不可用只记 `not_logged_in`。
5. `preflight --client all` 不得生成委托。
6. `subscribe` 不带 `--live` 走完整 dry-run。
7. 用户确认后才执行一次真实 live；先观察 F8、台账、截图，再扩大到全部账户。
8. `allotment` 走真实只读查询。

## 放行标准
- 两个客户端都能被唯一识别，且不会串窗、串进程、串账户。
- 每客户端动态识别最多 10 户；账户重排不需改代码。
- THS1、THS2 各自登录、切换、preflight、dry-run 全部有独立结果。
- 20 户或当前可用账户状态清单明确，华宝/中信建投不排除。
- 跨客户端重复账户不能产生第二次委托。
- 任何真实委托前均有 preflight、双开关、台账、F8 和截图。
- 测试全绿；不在本阶段处理 WebUI、密码自动化、券商并发 GUI。

## 结果

代码、配置和扩展能力已实施；真实客户端只读/登录链路已验收到当前周末可用状态；未产生真实委托。

- 新增 `execution/client_registry.py`、`execution/window_scope.py`、`execution/discovery.py`。
- `login.py`、`hexin_login.py`、`boot_login.py`、`ths_client.py`、`preflight.py`、`subscribe.py`、`allotment.py` 全部支持 client_id 隔离和串行。
- 订单台账 v2 使用稳定账户键，跨客户端重复资金账号阻断。
- 新增 `shared/paths.py`、`shared/errors.py`、`shared/doctor.py`、`shared/gui_lock.py`、setup/config 模板。
- `run.py` 新增 `doctor`、`discover`、`--client`，GUI 命令由跨进程原子锁保护。
- 自测：`python -m pytest -q` = 101 passed；`python run.py doctor` = ok；32 位依赖导入通过；setup.ps1 解析通过。
- 待交易日实测：THS1/THS2 discover 账户清单、boot-login、preflight、dry-run，再由用户确认一次 live。

## Rollback Plan

触发：窗口归属错误、误切账户、preflight 不通过、未确认委托、双实例干扰。

操作：停止任务 → `execution.clients.ths2.enabled=false` 或 `--client ths1` → 保存截图/台账 → 不重放不明订单。

恢复目标：10 分钟内回到 THS1 单实例链路。真实委托错误只能人工核对，不能靠代码回滚撤销。

## 2026-10-17 真实只读验收补充

- `python run.py discover --client all`：THS1 当前 8 户，THS2 当前 4 户，合计 12 户；配置动态匹配后 12/12，无重复资金账号。
- THS2 新发现 3 户：刘*伟、吴*聪、余*彬。吴*聪已映射到既有 `吴志聪PA` 并启用；刘*伟/余*彬已登记为停用占位，等待录入资金账号/权限后再启用。
- 首次 boot-login 暴露两个问题并已修：文本不可读时坐标兜底不能把“未确认”当成功；`about:blank` 不得误判密码/验证码弹窗。未匹配账户现在直接跳过委托界面切换。
- THS2 安全复跑 64 秒完成：未串户；检测到华宝委托下单登录框（交易密码/验证码）后按设计停止并报告 `dialog_required`，未绕过、未产生委托；当前菜单文本不可读，所以账户身份未能复核时保持 `not_selected`。
- 无任何真实委托。交易日仍需重跑 discover/boot-login/preflight/dry-run，再由用户确认 live。
