# Spec 总图 — 自动打新系统

本文件是项目级地图与索引，只管概览、地图、索引、全局规则摘要；详细需求进各子 spec。

## 子 Spec 索引

| 文件 | 内容 |
|---|---|
| `specs/requirements.md` | 需求与总体架构（业务目标、权限前置、时间节点、架构、里程碑） |
| `specs/security.md` | 安全规格（凭据存储、实盘开关、留痕要求） | ✅ |
| `specs/calendar.md` | 打新日历数据源与字段规格 | ✅ |
| `specs/notification.md` | 通知通道与消息格式规格 | ✅ |
| `specs/execution.md` | 券商客户端自动化规格（32 位 Python、依赖姿势、登录模式、安全约束） | ✅ |
| `specs/portability.md` | Windows 项目复制、路径、依赖、诊断与错误提示规格 | ✅ |
| `specs/operations.md` | 登录分类、客户端生命周期、开机错过后补和三类回执模板 | ✅ |
| `specs/ths-account-switch.md` | 单客户端切换同花顺登录账户、月度密码、资金账户和全流程规格 | ✅ |

## 系统逻辑图（2026-10-21 更新，完全本机运行，唯一模式 = 单同花顺切户）

> 2026-10-21 起 dual_client 双客户端模式彻底移除；唯一执行模式为 `ths_account_switch`，详见 `specs/ths-account-switch.md`。

```
Windows 计划任务（5 个）
├─ 登录 AutoIPO-BootLogin ────→ run.py ths-cycle --phase login（32位，延迟1分钟启动）
│     等网络就绪 → 对每个 THS 登录账户独立启动/恢复 hexin → 切换/登录 THS → 动态发现资金账户（每 THS 最多10户）
│     → F12 启动 xiadan → 校验账户列表+当前资金账号/显示名 → 输出会话状态 → 截图留痕/推送
│     → 温和关闭该 THS 会话 → 启动下一个 THS 登录账户
│     （“委托下单”登录框关闭后继续；其他安全验证弹窗停止，不自动绕过、不下单）
├─ 08:25 AutoIPO-DailyReport ─→ run.py daily-report（64位 Python）
│     东财API日历(当日+明日) → Server酱推送「10/15 华纬转债 1万张；…」
├─ 10:00 AutoIPO-Subscribe ───→ run.py ths-cycle --phase subscribe --live（32位 .venv32）
│     ├─ 东财API当日日历 → 指令清单（转债顶格/新股上限）
│     └─ 对每个 THS 登录账户独立执行：
│           启动 hexin → 登录 THS → 读取 xiadan 实际资金账户列表，动态匹配显示名/资金账号
│           → connect()（jqktrader+控件堆叠补丁）
│           → 批量新股申购页：读真实额度→剔0额度行→一键申购
│           → 未覆盖标的回退买入表单（双重保险，按代码去重）
│           → 每账户+代码写订单台账；同一交易日只提交一次
│           → F8 逐笔核验；不确定状态禁止自动重试
│           → 逐户记录 runtime_data/results/日期.json → 温和关闭该 THS 会话
│     └─ Server酱推送回执（标题含成败账户，正文逐户明细）
├─ 22:00 AutoIPO-Allotment-T1 → run.py ths-cycle --phase allotment（32位，T+1晚）
└─ 08:00 AutoIPO-Allotment-T2 → run.py ths-cycle --phase allotment（T+2早补查）
      逐账户切到「新股申购→查询中签明细」读网格
      → 有中签才推送：账户(客户端显示名)+标的中签数量+可用资金+缴款提醒
```

## 全局规则摘要

- 形态：完全本机 Windows 运行（服务器方案已否决）；券商密码 DPAPI 加密存本机 `config/secrets.yaml`。
- 券商接入：同花顺 hexin + F12 启动 xiadan + jqktrader 自动化；`ths_account_switch` 按 THS 登录账户独立启动/执行/关闭，单个 THS 登录账户最多处理 10 个资金账户。账户集合从当前菜单/xiadan 列表动态识别，所有券商和账户 ID 均不得硬编码。登录成功必须同时通过账户列表和当前资金账号/显示名校验。
- 实盘安全：每日订单台账 + 单账户单代码单日一次提交；`unknown`/`submitted_unverified` 一律阻断自动重试。
- 策略：批量申购页真实额度全申（0 额度自动剔除），日历买入表单兜底。
- 通知：Server酱；标题承载核心信息（手机只看标题）。回执正文=时间+账户（显示名/完整资金账号/THS 用户名）+事件，仅排除凭据。
- `execution.mode: live` + 命令行 `--live` 双保险；申购回执与中签通知为实盘关键推送。
- 非交易日不启动：所有计划任务与 catch-up 以东财上证指数日K线判定交易日，周末/节假日直接 `skipped_non_trading` 退出。
- 可复制性：项目内统一路径/依赖/诊断入口见 `specs/portability.md`；DPAPI 凭据换机必须重新录入。`python run.py doctor` 检查 64/32 位环境并输出错误码、原因、路径和修复动作。
- 工作规则见 `AGENTS.md`，文件索引见 `INDEX.md`。
- 顶层目标-判定-链路控制图见根目录 `逻辑图.MD`，随代码变更同步维护；与本文冲突时以代码真实行为修图并记录。

