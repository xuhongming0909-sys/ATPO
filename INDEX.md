# INDEX — 项目架构与文件索引

> 新建、移动或删除文件后必须更新本文件。单文档不得超过 500 行。

## 1. 架构总览

完全本机运行（Windows），无服务器、无强制 git 工作流；唯一执行模式 = 单同花顺切户（`ths_account_switch`）：

```text
Windows 计划任务 / 人工 CLI
  ├─ scheduler/    依赖安装、定时编排、交易日门、开机/联网 catch-up
  ├─ data_fetch/   打新日历抓取与规范化 + 沪深交易日判定
  ├─ execution/    同花顺切户串行自动化：启动→登录/切换→申购/查签→温和关闭
  ├─ notification/ Server酱与三类标准回执（时间+账户+事件全量显示）
  ├─ shared/       配置、路径、DPAPI、错误、诊断、GUI 锁、任务状态
  └─ runtime_data/ 日志、截图、生命周期、订单台账、任务状态、诊断
```

## 2. 目录职责

| 目录 | 职责 |
|---|---|
| `data_fetch/` | 新股/可转债日历抓取与字段规范化；沪深交易日判定 |
| `scheduler/` | Windows 计划任务、安装、日历推送、错过后补 |
| `execution/` | 客户端生命周期、THS 切户登录、申购、中签、订单台账 |
| `notification/` | Server酱通道、登录/申购/中签回执渲染与凭据排除 |
| `shared/` | 配置、路径、DPAPI、错误、doctor、GUI 锁、任务状态 |
| `config/` | 非敏感配置、配置模板、本机敏感配置 |
| `specs/` | 正式需求文档 |
| `missions/` | 最近任务档案 |
| `templates/` | 用户所有模板，AI 不修改 |
| `tests/` | 全 mock 测试 |
| `runtime_data/` | 运行时日志、截图、结果、台账、诊断 |
| `webui/` | 本机账户配置界面（独立工具，不参与定时链路） |
| `docs/` | 项目文档；多 AI git 协作规则 |

## 3. 文件摘要索引

### 入口与配置

| 文件 | 职责 |
|---|---|
| `run.py` | CLI 统一入口；GUI 命令转交 32 位环境；非交易日门与任务状态记录 |
| `config/config.example.yaml` | 非敏感配置模板 |
| `config/secrets.example.yaml` | 敏感配置结构模板 |
| `config/secrets.yaml` | 本机敏感配置；不展开、不进 git |
| `requirements.txt` | 64 位数据/通知端依赖 |
| `pytest.ini` | 限定 pytest 收集范围为 tests/（防 runtime_data 脚本被当测试收集） |
| `execution/requirements32.txt` | 32 位执行端固定依赖 |

### docs/

| 文件 | 职责 |
|---|---|
| `docs/multi_ai_git_workflow.md` | 多 AI 并行编码的分支、worktree、文件归属、提交合并规则 |

### shared/

| 文件 | 职责 |
|---|---|
| `shared/paths.py` | 项目、配置、运行时目录和相对路径统一解析 |
| `shared/config.py` | config.yaml 与 secrets.yaml 统一加载 |
| `shared/credstore.py` | Windows DPAPI 凭据加密 |
| `shared/errors.py` | 错误码、用户消息、修复提示；仅密码/验证码/SendKey/token/URL 脱敏，账户信息完整保留 |
| `shared/doctor.py` | 64/32 位环境、配置、DPAPI、客户端路径只读诊断（单模式） |
| `shared/gui_lock.py` | 跨进程 GUI 原子锁，防止双实例/计划任务抢 GUI |
| `shared/task_state.py` | 按任务/日期/模式保存幂等状态、回执状态和错误 |
| `shared/account_identity.py` | 统一账户身份字段（全量显示）与明细去重 |
| `shared/username_ocr.py` | THS 用户名 OCR + 网格屏幕 OCR；常驻 64 位 worker（--serve JSON 行，失败回退一次性子进程） |

### data_fetch/

| 文件 | 职责 |
|---|---|
| `data_fetch/calendar.py` | 东方财富打新日历抓取与规范化；进程内按日缓存 |
| `data_fetch/trading_days.py` | 沪深交易日判定：东财上证指数日K线 + 文件缓存 + 周末快速否决 |

### execution/

| 文件 | 职责 |
|---|---|
| `execution/client_registry.py` | 单同花顺客户端路径解析（ths_account_switch.hexin_path/xiadan_path） |
| `execution/window_scope.py` | 按精确 exe 路径隔离 PID/窗口 |
| `execution/client_lifecycle.py` | 进程归属、启动、温和关闭原语（GentleClientLifecycle 在 runner 复用） |
| `execution/account_session.py` | 账户会话结果、资金账号哈希工具 |
| `execution/hexin_login.py` | 主界面账户菜单识别、可直登账户登录、委托登录框关闭 |
| `execution/login.py` | F12 启动 xiadan、资金账号校验换户、会话复核、模态框清理（含一键打新：勾「不再自动弹出」后关窗）、截图留痕 |
| `execution/ths_account_config.py` | THS 登录账户配置、上限和 DPAPI 密码读取 |
| `execution/ths_account_switch.py` | THS 登录账户切换状态机、密码控件稳定元数据和结构化失败 |
| `execution/ths_account_model.py` | 资金账户标签解析、身份标识和唯一匹配模型 |
| `execution/ths_account_ui.py` | THS 主界面资金账户发现、点击后身份复核、登录弹窗关闭和 xiadan 切换 |
| `execution/ths_account_windows.py` | THS Win32 窗口识别、OCR 兜底、pywin32 密码控件元数据和账户控件操作 |
| `execution/ths_account_runner.py` | 每个 THS 账户独立生命周期、资金户任务执行、回执与状态落盘 |
| `execution/ths_client.py` | jqktrader 连接封装、控件堆叠补丁、网格屏幕 OCR 读取（read_grid_via_ocr） |
| `execution/captcha_login.py` | 登录弹窗验证码 OCR 自动填写 + DPAPI 密码自动填充（按资金账号匹配 secrets，WM_SETTEXT 写入，失败回退关框跳过） |
| `execution/ipo_page.py` | 批量新股申购页真实额度读取和一键申购 |
| `execution/subscribe.py` | 日历 allowlist 执行与买入表单兜底：台账、F8 核验、不确定状态禁止重试 |
| `execution/allotment.py` | 逐账户读取中签明细（屏幕 OCR，无剪贴板） |
| `execution/order_ledger.py` | 单账户单代码单日一次提交与不确定状态阻断 |

### notification/

| 文件 | 职责 |
|---|---|
| `notification/receipts.py` | 登录/申购/中签标准回执纯渲染（时间+账户+事件）、凭据排除和开关化发送 |
| `notification/serverchan.py` | Server酱推送封装，SendKey 不打印 |

### scheduler/

| 文件 | 职责 |
|---|---|
| `scheduler/jobs.py` | 打新日历抓取、格式化和推送 |
| `scheduler/catchup.py` | 开机/联网错过后补、交易日门、幂等判断、回执状态记录、ths-cycle 阶段编排 |
| `scheduler/setup.ps1` | 创建 64/32 位依赖环境并生成配置模板 |
| `scheduler/setup.cmd` | setup.ps1 双击入口 |
| `scheduler/register_tasks.ps1` | 注册/修复 Windows 计划任务（WakeToRun 睡眠唤醒） |
| `scheduler/run32.cmd` | 32 位 GUI/执行任务统一包装 |
| `scheduler/run64.cmd` | 64 位日历/通知任务统一包装 |
| `scheduler/package_project.ps1` | 项目复制打包 |

### webui/

| 文件 | 职责 |
|---|---|
| `webui/app.py` | 本机账户配置界面（独立工具；密码经 DPAPI 入 secrets.yaml） |

## 4. 关键运行链路

```text
登录（ths-cycle --phase login）：
  交易日门 → 全局 GUI 锁 → 逐 THS 账户：启动 hexin → 切换/登录 THS
  → 动态发现资金账户（每 THS ≤10 户）→ F12 启动 xiadan → 身份复核
  → 登录回执 → 温和关闭该会话 → 下一 THS 账户

申购（ths-cycle --phase subscribe --live）：
  交易日门 → 日历 → allowlist（转债顶格/新股上限，blacklist 排除）
  → 逐 THS 账户串行：启动→登录→连接 jqktrader
  → 批量申购页读真实额度→剔 0 额度→一键申购→未覆盖标的买入表单兜底
  → 每账户+代码写订单台账（单日恰一次）→ F8 核验（不明禁止重试）
  → 申购回执 → 温和关闭

中签（ths-cycle --phase allotment / allotment 命令）：
  交易日门 → 归属最近申购业务日 → 逐账户读中签明细 → 中签回执 → 温和关闭

catch-up（开机/联网）：
  等网络 → 交易日门 → 补日历推送 → 窗口内补申购 → 补中签/回执（幂等）
```

## 5. 定时与补任务

| 任务计划名称 | 触发 | 动作 |
|---|---|---|
| `AutoIPO-BootLogin` | 用户登录 + 1 分钟 | `run.py ths-cycle --phase login` |
| `AutoIPO-DailyReport` | 工作日 08:30 | `run.py daily-report` |
| `AutoIPO-Subscribe` | 工作日 10:00 | `run.py ths-cycle --phase subscribe --live` |
| `AutoIPO-Allotment-T1` | 工作日 22:00 | `run.py ths-cycle --phase allotment` |
| `AutoIPO-Allotment-T2` | 工作日 08:00 | `run.py ths-cycle --phase allotment` |
| `AutoIPO-CatchUp-Logon` | 用户登录 + 2 分钟 | `run.py catch-up --live` |
| `AutoIPO-CatchUp-Network` | 网络配置启用事件 | `run.py catch-up --live` |

工作日触发由计划任务（周一至周五）粗筛，节假日由 `data_fetch/trading_days.py` 精确跳过。

## 6. 不变量

- `ths_account_switch` 每个 THS 登录账户独立启动/关闭并严格串行（全局 GUI 锁）。
- 每 THS 登录账户最多 10 个资金账户，账户集合动态识别，券商/账号不硬编码。
- 「委托下单」登录框允许自动处理（验证码 OCR / DPAPI 密码填充后点登录，失败回退关框跳过）；短信、动态口令、人工安全验证弹窗绝不绕过。
- 其他安全验证弹窗停止当前客户端，不自动绕过。
- GUI 任务后温和关闭客户端，禁止强杀；关闭失败报 CLIENT_CLOSE_FAILED。
- 交易密码、验证码、SendKey、token、DPAPI 密文不进代码、git、日志或推送；账户识别信息（显示名/完整资金账号/THS 用户名）全量显示。
- 非交易日不启动任何任务（周末/节假日 skipped_non_trading）。
- `execution.mode=live` 与 `--live` 同时满足才允许真实委托；单账户单代码单日一次；结果不明禁止自动重试。

