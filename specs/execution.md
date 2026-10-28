# Execution 模块规格（券商客户端自动化）

## 1. 范围

本模块负责同花顺客户端生命周期、动态账户识别、登录/换户、申购、中签查询和订单留痕。只在本机交互桌面运行；不提供远程代操作。

不在本模块内处理打新日历抓取、计划任务注册和推送模板格式。

## 2. 技术路线

- 同花顺主客户端：`hexin.exe`，负责账户菜单和 F12 会话入口。
- 同花顺下单客户端：`xiadan.exe`，负责账户切换、批量新股申购、买入表单、F8 委托查询和中签查询。
- 自动化库：jqktrader + pywinauto；执行端必须使用项目 `.venv32`（32 位 Python 3.11）。
- 依赖固定：`pandas==2.0.3`、`numpy<2`；jqktrader/easyutils 用 `--no-deps` 安装后再装 `execution/requirements32.txt`。
- `run.py` 的 GUI 命令自动转交 `.venv32/Scripts/python.exe`；日历和通知可使用 64 位 Python。

## 3. 双实例模型与可复制性

- `config/config.yaml → execution.clients` 注册客户端；每项包含 `enabled`、`hexin_path`、`xiadan_path`。
- 单客户端单顺序：按 `execution.ths_account_switch.accounts` 配置顺序严格串行。
- 所有进程、窗口、F12、账户下拉、jqktrader 连接、截图和弹窗清理必须绑定 `client_id`。
- 全局 `shared/gui_lock.py` 覆盖整个多客户端任务；两个同花顺实例严格串行，绝不并发抢 GUI。
- 进程归属按精确 exe 路径和 PID 判断；同名但路径不同的进程不得归属到本客户端。
- 每实例最多处理当前实际列表中的 10 个已登录账户。目标约 20 户时使用两个实例，不突破单实例容量。
- 账户按 `display_name`、`id`、`alias/aliases` 和资金账号哈希动态匹配 config；不得硬编码券商、资金账号、账户 ID 或菜单行。
- 一个客户端失败不阻塞另一个客户端；结果必须按 `client_id` 分开输出进程、账户、状态、错误和截图路径。
- 项目文件夹可复制到其他 Windows 电脑。换机后运行 `scheduler/setup.ps1`、重新录入 DPAPI 敏感项、执行 `python run.py doctor`，再注册计划任务。

## 4. 客户端生命周期

每个 THS 登录账户由 `execution/ths_account_runner.py` 和 `execution/client_lifecycle.py` 包装：

```text
获取全局 GUI 锁
  → 选择下一个 THS 登录账户
  → 启动或恢复该账户会话的 hexin/xiadan
  → 登录 THS 账户并处理该账户下最多 10 个资金账户
  → 执行阶段任务
  → 保存结果、截图和生命周期记录
  → 温和关闭该 THS 账户客户端
  → 释放全局锁
```

- 任务前不需要客户端常驻；需要时启动，任务结束关闭。
- 进程记录 `managed` 或 `preexisting`，并保存 PID、启动状态和关闭状态。
- 默认 `close_after_task=true`、`close_preexisting=true`、`close_timeout_s=15`。
- 当前运行器从 `execution.lifecycle` 读取生命周期参数；未配置时使用上述默认值。
- 关闭只发送关闭消息并等待退出；禁止 `taskkill /f` 或其他强杀。
- 启动一半失败时清理本次已启动的受管进程。
- 关闭失败报 `CLIENT_CLOSE_FAILED`，保留进程并要求人工关闭；不得伪报任务完成。
- 生命周期 JSON 写入 `runtime_data/client_lifecycle/`。

## 5. 主界面账户登录

### 5.1 候选识别

1. 打开主界面右上角账户下拉。
2. 读取菜单行文本。
3. 按 `display_name`、`id`、`alias/aliases` 唯一匹配 config 账户。
4. 只有带姓名/别名特征的行才是“可直接登录账户”。
5. 只有证券公司 + 资金账号、没有姓名/别名的行标记 `login_required`，不主动点击。
6. `menu_row` 只能在多个同名行中辅助选择；文本不可读时禁止坐标盲点。

### 5.2 单实例 10 户上限

- `gui.hexin_login.max_accounts` 和 `boot_login.max_accounts` 默认 10。
- `ready` 与 `already_logged_in` 都计入已登录容量。
- 达到 10 户后停止点击，其余账户记 `not_selected`。
- 已登录账户优先识别，不重复点击。
- 华宝、中信建投等暂时无法登录的账户只记本批次 `login_required`，不得永久排除。

### 5.3 登录成功判据

点击后必须同时满足：

- 委托账户列表新增或包含目标显示名。
- 当前资金账号与 config 对应的 `fund_account_hash` 一致。

标签匹配但当前资金账号/显示名不符记 `wrong_account`；切换失败记 `switch_failed`；身份上下文不可读记 `xiadan_failed`。不得把“下拉里有名字”单独视为登录成功。

### 5.4 会话状态

统一字段：

```text
account_id
display_name
fund_account_hash
main_menu_row
xiadan_present
current_fund_account
status
error
client_id
```

状态至少包括：

- `ready`
- `already_logged_in`
- `login_required`
- `dialog_closed`
- `not_selected`
- `wrong_account`
- `switch_failed`
- `not_logged_in`
- `dialog_required`
- `menu_failed`
- `xiadan_failed`
- `config_missing`

运行时保存完整 THS 用户名、账户显示名、状态、错误和已验证行号；完整资金账号只放 `config/secrets.yaml`，不在日志/推送正文展开。

## 6. 弹窗分类与处理

### 6.1 “委托下单”登录框

标题含“委托下单”，控件含资金账号、交易密码或验证码时（2026-10-24 用户批准自动登录）：

1. 先保存截图。
2. 尝试自动处理（按序，任一成功即复查身份后记 `ready`）：
   - 只含验证码（密码已保存）：OCR 数字验证码填入 + 点登录。
   - 含空密码框：`config/secrets.yaml` 按资金账号匹配 `password_enc` → DPAPI 解密 → WM_SETTEXT 写入密码框 → 勾「保存密码」→ 填验证码 → 点登录。
3. 自动处理任一步失败或密码未录入：发送 `WM_CLOSE` 关闭登录框，当前账户记 `dialog_closed`/`login_required`，继续下一户。
4. 交易密码绝不进日志/推送/剪贴板；短信、动态口令、人工安全验证弹窗仍停止并推送。

### 6.2 其他安全弹窗

身份验证、安全验证、人工确认等非委托登录框：

- 保存截图。
- 停止当前客户端剩余自动登录或操作。
- 标记 `dialog_required` 并报告错误码。
- 不自动确认、不绕过、不伪造成功。

## 7. 委托界面登录与换户

- `xiadan.exe` 必须由对应 `hexin.exe` 以 F12 带会话令牌启动；裸启动为游客态，不作为正常链路。
- 顶栏账户下拉必须真实点击目标行。只改 ComboBox 显示文字不会切换账户上下文。
- 切换成功以当前资金账号刷新并通过哈希校验为准。
- `execution/login.py::ensure_logged_in(account_id)` 用于申购/中签前切换。
- `runtime_data/account_map.json` 存资金账号哈希、已验证显示名和行号缓存（本人本机可用完整资金账号辅助识别）。

## 8. 开机登录链路

```text
等网络
  → 启动/恢复目标 hexin
  → 账户菜单逐户识别并登录可直登账户
  → 遇“委托下单”登录框则截图、关闭、继续
  → F12 启动 xiadan
  → 读取账户列表并逐户切换复核资金账号
  → 保存截图和会话状态
  → 发送登录回执
```

- `python run.py ths-cycle --phase login`。
- 网络探活见 `boot_login.probe_url`、`network_timeout_s`。
- 登录只做会话准备，不下单，不受 `execution.mode` 控制。

## 9. 申购执行

- 主路径：`execution/ipo_page.py` 打开“批量新股申购”，读取柜台真实额度，剔除 0 额度后提交。
- 兜底路径：`execution/subscribe.py` 使用“买入申购代码”表单处理可转债和批量页漏项。
- 可转债按申购代码和市场规则生成顶格数量；新股按发行价和申购上限生成数量。
- config 的 `permissions` 只作预过滤，最终以柜台真实额度为准。
- 同一账户、同一申购代码、同一交易日只允许提交一次。
- 批量提交后读取 F8 当日委托逐笔核验；弹窗成功文字不是独立成功判据。
- `unknown`、`submitted_unverified` 记入订单台账并阻断自动重试。
- `execution.mode=live` 与命令行 `--live` 同时满足才真实下单；缺一为 dry-run。

## 10. 中签查询

- 逐账户切换到“新股申购 → 查询中签明细”读取网格。
- 输出账户显示名、完整资金账号、标的、证券代码、中签数量、缴款金额、状态和错误。
- 查询成功且无记录可作为最终无中签；数据未公布或查询失败不得当作最终结果。
- 查询逻辑不依赖推送结果；推送失败不得伪造查询成功。

## 11. 安全与留痕

- `execution.mode` 默认 `dry_run`。
- 每次真实委托保存订单台账和客户端截图到 `runtime_data/`。
- 资金账号、持仓和余额只用于本地判断；不进代码、日志、文档或推送。
- 不自动输入交易密码、不识别验证码、不绕过安全确认。
- execution 测试必须使用桩对象，永不连接真实券商客户端。

## 12. 只读入口

- `python run.py doctor`：只读检查环境、配置、DPAPI 与客户端路径。
- `python run.py doctor`：只读检查 64/32 位环境、配置、DPAPI、客户端路径和运行目录。

