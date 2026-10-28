# 自动打新系统

可转债 + 新股自动登录、申购、中签查询和标准回执。仅限本机 Windows 自用。

## 核心行为

- 唯一模式 `ths_account_switch`：按同花顺登录账户独立开一段生命周期：启动同花顺 → 登录目标 THS 账户 → 处理资金账户 → 执行阶段 → 温和关闭 → 下一个 THS 账户。
- 单个同花顺客户端最多管理 10 个 THS 登录账户；每个 THS 登录账户最多处理 10 个资金账户。账户按当前菜单/委托列表动态匹配，不硬编码券商、账号或菜单行。
- 只点击可直接登录账户。需填资金账号、交易密码或验证码的账户跳过。
- 误点“委托下单”登录框时，先截图、关闭弹窗，再继续处理下一账户；不填密码、不识别验证码。其他身份验证、安全验证或人工确认弹窗才停止当前客户端。
- GUI 任务前启动所需客户端，任务结束后温和关闭；不使用强杀。预存在进程默认也温和关闭，关闭失败明确报告。
- 开机或联网后补当日遗漏任务：申购过时不补，中签结果未定或回执未成功则继续补查。
- 登录、申购、中签使用统一回执模板；THS 用户名、账户显示名、资金账号/尾号、状态、错误和业务明细正常显示，便于识别具体账户。仅密码、验证码、SendKey、token、DPAPI 密文等凭据排除。

## 系统结构

```text
scheduler/    Windows 计划任务、开机/联网 catch-up、依赖安装
data_fetch/   打新日历抓取与规范化
execution/    同花顺启动/关闭、账户识别、登录、申购、中签、订单台账
notification/ Server酱与登录/申购/中签标准回执
shared/       配置、路径、DPAPI、错误、诊断、GUI 锁、任务状态
runtime_data/ 日志、截图、生命周期记录、任务状态、订单台账
```

## 新电脑部署

目标是复制项目文件夹后初始化运行；Python 与同花顺客户端是外部依赖，不打包成免安装 EXE。

1. 安装 64 位 Python 3.12、32 位 Python 3.11，并安装两个同花顺客户端。
2. 复制项目文件夹。发布包不得包含 `.venv32/`、`runtime_data/`、`config/secrets.yaml`。
3. 初始化依赖和配置模板：

```powershell
cd <项目目录>
powershell -ExecutionPolicy Bypass -File scheduler\setup.ps1
```

4. 在 `config/config.yaml → execution.clients` 填写两个客户端的 `hexin_path`、`xiadan_path`。
5. 在 `config/config.yaml → accounts` 登记账户，在 `config/secrets.yaml` 录入完整资金账号和 DPAPI 密文。DPAPI 只对原电脑原 Windows 用户有效，换机必须重新录入。
6. 只读诊断：

```powershell
python run.py doctor
```

7. 注册 Windows 计划任务：

```powershell
powershell -ExecutionPolicy Bypass -File scheduler\register_tasks.ps1
```

## 常用命令

```powershell
python run.py doctor
python run.py calendar --day YYYY-MM-DD
python run.py daily-report
python run.py ths-cycle --phase login
python run.py ths-cycle --phase subscribe [--live] [--date YYYY-MM-DD]
python run.py ths-cycle --phase allotment [--date YYYY-MM-DD]
python run.py allotment
python run.py catch-up [--date YYYY-MM-DD] [--live]
python run.py schedule-json
python run.py notify-test
```

- GUI 命令（`ths-cycle` / `catch-up`）自动转交项目 `.venv32`（32 位 Python 3.11）。
- 申购默认 dry-run；只有 `config execution.mode=live` 与命令行 `--live` 同时满足才产生真实委托。
- 非交易日（周末/节假日）所有任务自动跳过（`skipped_non_trading`），判定来源为东财上证指数日K线。
- `catch-up` 先等待网络；申购超过 `catchup.subscribe_skip_after` 记 `skipped_expired`，不补真实委托。

## 登录与弹窗规则

1. 打开主界面账户下拉，按 `display_name`、`id`、`alias` 唯一匹配账户。
2. 有姓名/别名特征的行才是可直接登录候选。
3. 只显示证券公司 + 资金账号、没有姓名/别名的行记为 `login_required`，默认不点。
4. 已登录账户优先计入单实例 10 户上限，并用资金账号哈希复核。
5. 点击后必须同时确认委托账户列表和当前资金账号；标签存在但哈希不符记 `wrong_account`。
6. “委托下单”资金账号/密码/验证码框：立即截图并关闭，目标账户记 `dialog_closed` 或 `login_required`，然后继续。
7. 其他身份验证、安全验证或人工确认框：停止当前客户端剩余登录，保存截图并报告 `dialog_required`。

## 客户端生命周期

每个 THS 登录账户独立执行：

```text
获取全局 GUI 锁
  → 启动或恢复目标 hexin
  → 登录一个 THS 账户并处理该账户下最多 10 个资金账户
  → 执行 login/subscribe/allotment 阶段并保存结果/截图
  → 温和关闭本次该 THS 账户启动的客户端
  → 释放锁后为下一个 THS 账户重新启动
  → 释放锁
```

- 进程归属按精确 exe 路径和 PID 记录，不按同名进程猜测；两个 THS 账户之间不复用上一个账户的窗口状态。
- 默认温和关闭并等待退出；禁止 `taskkill /f` 或直接强杀。
- 关闭失败报 `CLIENT_CLOSE_FAILED`，不得伪报完成。
- 生命周期记录写入 `runtime_data/client_lifecycle/`。

## 错过后补与幂等

- `runtime_data/task_state.json` 按任务、业务日期、模式记录状态和回执状态；dry-run 与 live 分离。
- 已完成且回执已成功或明确跳过的任务不重复执行。
- 日历推送未成功则补发。
- 申购只在当日且未超过 `catchup.subscribe_skip_after` 时补做；过期记 `skipped_expired`。
- 中签结果未公布、查询失败或回执未成功时继续补查；“数据未公布”不是最终无中签。
- 订单结果不明记 `blocked_uncertain`/`submitted_unverified`，禁止自动重复下单。回执失败不触发重复申购，只补回执或人工核对。

## 标准回执

- 登录：`[登录回执][M/D] 成功 X｜需登录 X｜失败 X`
- 申购：`[申购回执][M/D] 成功 X｜跳过 X｜失败 X`
- 中签：`[中签回执][M/D] 中签 X 户`；无中签为 `[中签回执][M/D] 无中签`

正文固定包含日期、结果、逐客户端或逐标的信息、失败原因和下一步。普通账户识别信息（含资金账号/尾号）可以显示；不得显示交易密码、验证码、SendKey 或 token。详细契约见 `specs/notification.md`。

## 安全边界

- `execution.mode` 默认 `dry_run`；实盘必须 config 显式改为 `live` 且命令行加 `--live`。
- 完整资金账号的配置来源只存 `config/secrets.yaml`，交易密码只存 DPAPI 密文；凭据不进代码、git、日志或推送。普通账户识别信息可在本机日志和本人推送中显示。
- 每次真实委托必须有订单台账和客户端截图；结果不明时禁止自动重试。
- 不自动填写交易密码、不识别验证码、不绕过人工安全确认。

## 文档导航

- 工作规则：`AGENTS.md`
- 文件索引：`INDEX.md`
- 顶层逻辑图（目标→判定→链路控制）：`逻辑图.MD`
- 需求总图：`specs/spec.md`
- 需求与架构：`specs/requirements.md`
- 执行与双实例：`specs/execution.md`
- 登录、生命周期、补任务和回执：`specs/operations.md`
- 通知模板与脱敏：`specs/notification.md`
- 复制与诊断：`specs/portability.md`
- 安全：`specs/security.md`

