# Mission Plan 模板

## 步骤
1. 按 Read Order 核对项目架构、正式 spec、配置、MEMORY 和近期 mission。
   验证：确认当前为完全本机 Windows、5 个计划任务、live 执行链和 DPAPI 凭据边界。
2. 核对真实运行环境与外部依赖。
   验证：记录 64 位 Python 3.12.10、32 位 Python 3.11.9、`.venv32`、`xiadan.exe`、任务计划和项目代码规模。
3. 核对官方打包/调度文档。
   验证：PyInstaller 6.22.3 官方文档可访问；Windows Task Scheduler 与 Inno Setup 官方页面可访问。
4. 对比独立应用形态并评估风险。
   验证：每个风险绑定当前项目直接证据、影响和缓解措施。
5. 输出分阶段计划、成功标准和 rollback plan。
   验证：基线测试真实通过；计划不执行任何实盘委托。

## 验证结果

### 1. 当前项目直接证据

- `run.py` 是统一 CLI：`calendar / notify-test / daily-report / subscribe / allotment / boot-login / preflight / webui`。
- Windows 任务计划现有 5 项：`AutoIPO-BootLogin`、`AutoIPO-DailyReport`、`AutoIPO-Subscribe`、`AutoIPO-Allotment-T1`、`AutoIPO-Allotment-T2`。
- `scheduler/register_tasks.ps1` 用 `LogonType Interactive`。这符合 UI 自动化要求：不能改造成普通 Windows Service，必须运行在用户已登录的交互桌面。
- 执行链依赖外部同花顺：`E:\同花顺\同花顺\xiadan.exe` 真实存在，大小 `86,568,672` bytes；同花顺主客户端还必须保持登录并通过 F12 令牌拉起 xiadan。
- 项目是双架构：
  - 64 位 Python `3.12.10 (AMD64)`：日历、通知、调度。
  - 32 位 Python `3.11.9 (Intel)`：`.venv32`、jqktrader/pywinauto/客户端自动化。
- `.venv32` 依赖包含 `jqktrader`、`pywinauto`、`numpy`、`pandas`、`pywin32/comtypes`、OpenCV/PIL 等；其本身没有 `pytest`。测试基线用 64 位环境执行。
- `python -m pytest -q` 真实结果：`76 passed in 11.98s`。
- `config/secrets.yaml` 中的交易密码走 Windows DPAPI，绑定当前 Windows 用户。打包后密文可外置，但换机器/换用户不能解密，必须重新录入。
- 当前路径大量依赖项目根目录：`config/`、`runtime_data/`、图片模板、日志、截图和台账。封装后必须区分只读程序资源与可写用户数据。
- `webui/app.py` 标记“已停用”，依赖 Flask + ruamel.yaml；这些依赖不在根 `requirements.txt`。是否纳入独立应用必须先定需求，不能默默打包。
- 当前 `config.execution.mode=live`，且计划任务带 `subscribe --live`。封装回归若发生错配，风险直接落到真实委托。

### 2. 官方文档核对（2026-10-17）

- PyInstaller：本次 PyPI 与官方文档均为 `6.22.3`，支持 Python `>=3.8,<3.16`。
  - [Requirements](https://pyinstaller.org/en/stable/requirements.html)
  - [What PyInstaller Does](https://pyinstaller.org/en/stable/operating-mode.html)
  - [Spec Files](https://pyinstaller.org/en/stable/spec-files.html)
  - [Common Issues and Pitfalls](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html)
- 官方文档明确区分 one-folder 与 one-file；one-file 会在运行时解包到临时目录，动态加载 DLL/资源更容易出问题。官方还明确 PyInstaller 不是可靠的源码保密方案。
- [Microsoft Task Scheduler](https://learn.microsoft.com/windows/win32/taskschd/task-scheduler-start-page)：继续作为 Windows 原生调度入口。
- [Inno Setup](https://jrsoftware.org/isinfo.php)：可作为后续 Windows 安装器；不是首阶段必要项。

## 形态结论

| 形态 | 可行性 | 结论 |
|---|---|---|
| A. 独立目录应用包（onedir + 双 EXE + 启动器） | 高 | **推荐首阶段**。无需用户装 Python；保留 Windows 任务和同花顺依赖；最稳 |
| B. Windows 安装包（A + Inno Setup + 代码签名） | 中高 | 适合固定电脑长期使用；升级、ACL、任务注册、卸载更规范 |
| C. 一个 `自动打新.exe` 单文件 | 低 | 不推荐。一个 EXE 无法同时承载 32/64 位解释器；one-file 临时解包与动态 DLL 风险高 |
| D. 完整原生桌面 GUI 重写 | 中 | 可做，但属于新产品开发，不是简单封装；投入大、回归面大 |
| E. 发给别人双击即可代打新 | 不可行 | 受同花顺安装/登录、账户资料、DPAPI、券商协议、UI 版本和实盘风险限制 |

### 推荐目标形态

定义为“本机独立应用包”，不是“单文件”，也不是“跨机器免安装代交易”：

```text
自动打新/
├─ AutoIPO.exe                 # 64 位启动器/状态界面/诊断/任务管理
├─ AutoIPO.Core.exe            # 64 位：日历、通知、调度入口
├─ AutoIPO.Execution32.exe     # 32 位：登录、申购、中签、preflight
├─ app/                        # onedir 运行时，只读
└─ data/                       # config、secrets、日志、截图、台账，可写
```

- 同花顺 `hexin.exe/xiadan.exe` 不打进包内。打包第三方券商客户端会放大许可、体积、升级和安全风险。
- 调度仍用 Windows Task Scheduler。安装/首次运行时幂等注册，任务必须是 Interactive。
- 首阶段优先“独立目录”。单文件仅可用于极小的启动器，不承载业务执行链。

## 风险矩阵

| 风险 | 概率/影响 | 项目证据 | 缓解 |
|---|---|---|---|
| 同花顺升级导致控件/菜单失效 | 高/高 | 大量 pywinauto 控件、模板、坐标兼容逻辑 | 版本检测、preflight 门禁、失败即停、保留旧包、升级先 dry_run |
| 实盘回归导致误申购/漏申购 | 中/极高 | `mode=live` + `--live`，10:00 自动执行 | 打包期强制 dry_run；上线前 shadow run；单账户/单标的 canary；保留订单台账 |
| 32/64 位依赖无法打成一个包 | 高/高 | Python 3.11-32 + Python 3.12-64 双运行时 | 双 EXE + 启动器；不追求单文件 |
| one-file 临时解包、DLL/模板丢失 | 中/高 | OpenCV、pywin32、COM、图片模板 | 业务链全部 onedir；资源显式收集；干净机测试 |
| Windows Service 锁屏后 UI 自动化失效 | 高/高 | 账户下拉必须真实鼠标点击；任务必须 Interactive | 保持登录会话；关显示器可，Win+L/锁屏不可；服务化否决 |
| 路径随安装位置变化 | 高/中 | 当前 `ROOT/config`、`ROOT/runtime_data` | 程序只读与用户数据分离；禁止 `cwd` 隐式依赖；路径测试 |
| DPAPI 密文换机/换用户不可用 | 高/高 | `shared/credstore.py` + `win32crypt` | 安装不复制明文；迁移向导要求重录密码；备份说明写清 |
| 杀毒误报/SmartScreen 拦截 | 中/高 | 自动化 + 未签名 EXE + 实盘类软件 | 官方 PyInstaller；onedir；代码签名；发布哈希；干净机验证 |
| WebUI 被误当远程管理入口 | 中/高 | Flask 表单可改 live/密码 | 首阶段默认不打包 WebUI；若纳入，只绑 `127.0.0.1`，不监听局域网 |
| 东财接口/字段变化 | 中/中 | `data_fetch/calendar.py` 直连外部 API | 错误不伪装空日历；接口契约测试；版本化适配 |
| 配置/日志/截图泄密 | 中/高 | secrets、截图、台账在可写目录 | 外置 data 目录 ACL；日志脱敏；打包前 secret scan；测试包不放真实 secrets |
| 升级/卸载误删用户数据 | 中/高 | 订单留痕和 DPAPI 是审计/恢复资产 | 升级不覆盖 data；卸载默认保留；显式“彻底删除”二次确认 |

## 分阶段实施计划

### Phase 0：冻结封装需求

1. 用户选定 A/B/C/D；确认是否需要图形界面、是否需要安装器、是否允许同花顺作为外部依赖。
2. 新增正式 `specs/packaging.md`，写清支持的 Windows 版本、便携/安装模式、UI 范围、升级和数据目录。
3. 若需要 `packaging/` 顶层目录，先请用户批准 AGENTS.md 白名单变更。

验证：spec 明确“独立”的边界；没有“单 EXE 自带同花顺/跨机密码”这类不可交付承诺。

### Phase 1：行为与安全基线

1. 固定基线：76 tests 全通过；导出 5 个任务 XML；记录 EXE/配置版本；做 secret scan。
2. 打包阶段默认把 `execution.mode` 保持 `dry_run`，不把 `--live` 写进首次安装任务。
3. 定义验收命令：`calendar --day`、`daily-report --day`、`preflight`、`notify-test`；真实下单不属于自动验收。

验证：测试通过；导出任务不含明文秘密；dry-run 门禁生效。

### Phase 2：路径与双运行时打包 POC

1. 抽出 `program_dir/data_dir/resource_dir` 解析，不再依赖当前工作目录。
2. 建 64 位 `AutoIPO.Core.exe` 与 32 位 `AutoIPO.Execution32.exe`，均用 PyInstaller 6.22.3 onedir。
3. 显式收集 `tpl_account_btn.png`、YAML 模板和动态库；webui 暂不打包。
4. 启动器只负责状态、手动触发、日志入口和任务注册，不替代调度器。

验证：无 Python 的干净 Windows 用户/虚拟机能启动；两个 EXE 各自 `--help`；抓取真实日历；preflight 只读通过；程序目录删除后数据仍可恢复。

### Phase 3：任务、升级和安装

1. 幂等注册 5 个 Interactive 任务，路径指向 EXE，不指向 `.cmd/.venv`。
2. 升级流程：停止任务 → 备份程序与任务 XML → 替换 app → preflight → 恢复任务。
3. 如需 B：Inno Setup 安装器 + 代码签名 + “保留/彻底删除数据”卸载选项。

验证：重复安装不产生重复任务；断电/中断后可回滚；卸载默认不删 secrets/台账。

### Phase 4：实盘分级放行

1. 先连续 2 个交易日 dry-run/shadow，核对账户、额度、指令、截图、台账。
2. 再做人工确认的单账户/单标的 live canary。
3. 最后恢复全账户；观察 F8 核验、失败阻断、中签去重和异常推送。

验证：任何 `unknown/submitted_unverified` 均不重试；错误委托可从截图+台账定位；不出现明文密码。

## 成功标准

- 双击 `AutoIPO.exe` 可查看状态、运行 preflight、打开日志，不需用户手动激活 Python 环境。
- 两个业务 EXE 在干净 Windows 环境运行；同花顺是唯一外部业务客户端依赖。
- 5 个计划任务正常注册并在登录交互会话执行。
- `python -m pytest -q` 前后均为 76 passed 或新增测试全通过。
- 真实日历调用有输出；测试推送可用；preflight 通过；自动验收永不真实下单。
- secrets 不进 EXE/安装包/git/日志/推送；换机只提示重新录入。
- 升级、卸载、失败回滚不会覆盖或误删订单台账、截图、DPAPI secrets。

## Rollback Plan

- 触发条件：EXE 无法启动、任务路径错误、preflight 失败、同花顺控件不匹配、任何疑似误委托。
- 操作：立即停用新任务 → 恢复任务 XML → 恢复上一版 app 目录 → 运行 `preflight` → 保持 `dry_run`，不自动重放申购。
- 数据：升级前只备份 `config/` 与 `runtime_data/` 中审计资产；备份文件用 DPAPI 保护或限制本机用户 ACL。
- RTO：10 分钟内恢复旧版调度；真实委托错误无法“代码回滚”，只能靠事前 dry-run、单次台账、F8 核验和人工处置。

## 结果
完成分析。结论：封装为“本机独立目录应用包”可行；封装为“单个完全独立 EXE/跨机器免配置代交易”不现实。

## 风险与遗留
- 最大风险不是 PyInstaller，而是同花顺 UI 自动化、32 位执行环境和 live 交易回归。
- 下一步必须先确认目标形态 A/B/C/D 与 UI 范围，再更新正式 spec 和实现。
- `.venv32` 未安装 pytest；若打包后要跑 32 位集成测试，需要单独补测试环境，不能复用当前 76 个测试结论替代。
