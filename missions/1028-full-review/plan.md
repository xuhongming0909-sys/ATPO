# Mission Plan

## 步骤

1. 按 Read Order 读取 AGENTS、INDEX、逻辑图、README、全部 specs、非敏感配置和最新 MEMORY；验证：文档已读且记录冲突。
2. 盘点代码、测试、脚本、配置样例与仓库状态；验证：文件清单、行数、git 状态齐全。
3. 审查业务主链路：交易日门、日历、调度、catch-up、GUI 锁、生命周期、登录、申购、中签、订单台账。验证：关键函数与异常路径均有代码证据。
4. 审查横切面：配置、凭据、脱敏、路径可移植性、错误处理、日志、并发、线程、幂等。验证：安全规则逐项核对。
5. 运行只读验证：测试、编译、CLI help、doctor（必要时）；验证：记录退出码、通过/失败数和限制。
6. 汇总按 Critical / High / Medium / Low 分级，更新本 mission 的验证结果、结论和风险。

## 验证结果

- `pytest -q -p no:cacheprovider --basetemp=runtime_data\testtmp-review-1028-final -k 'not test_chain_lock_breaks_when_owner_process_dead'`：329 passed，1 deselected。
- 全量 pytest 直接运行被两处环境/测试隔离问题阻断：沙箱默认临时目录 ACL 拒绝访问；现存 `runtime_data/catchup.lock` 使测试前置断言失败。测试数据已清理。
- 64 位 compileall：通过。
- 32 位 compileall：通过。
- `run.py doctor`（沙箱外只读）：`ok=true`；64/32 位依赖、配置、客户端路径、DPAPI 检查通过。2 个 THS 密码密文缺失，仅为 warning。
- `run.py schedule-json`：08:30 / 10:00 / 22:00 / 08:00。
- 7 个 AutoIPO 计划任务均存在且 Ready；WakeToRun=true（网络事件任务除外）。
- 32 位 `pip check`：失败。`easyutils` 缺 `pyquery`，`jqktrader` 缺 `pypiwin32` 且声明 `pandas<2`，实际为 2.0.3。
- 反例复现：T+1 22:00 后中签查询失败且无 items，编排结果为 `completed`；`batch_rejected` 申购行也会被判为 `completed`。
- 反例复现：未来工作日节假日 `2027-01-01` 被判为交易日。
- 反例复现：回执 `reason` 为嵌套映射时，`password=top-secret` 原样进入正文。
- 并发修改后已按 14:17 最新源码复跑：329 passed、1 deselected；64/32 位 compileall 均通过。

## 结果

结论：Request changes。业务骨架、安全门、订单台账和 mock 测试总体扎实，但当前快照不适合继续无人工盯守的实盘自动运行。

### Critical

1. `execution/ths_account_runner.py:848` 每户任务放入 daemon 线程，超时后仅 `join` 返回并继续下一户，旧线程仍可操作同一 GUI；实盘可能跨户并发点击或提交。
2. `scheduler/catchup.py:273`、`scheduler/catchup.py:445` 只要超过 T+1 22:00 且 items 为空，就把中签查询判 completed；查询失败会被伪装成“无中签”，并阻止后续补查。

### High

3. `shared/username_ocr.py:350` 生产 grid 模式未传 `header_keys`，表头校验失效；F8、申购、中签均可能把错误网格当有效表格。
4. `scheduler/catchup.py:435` 未把 `batch_rejected` 视为失败；已复现批次拒绝被记 completed。
5. `data_fetch/trading_days.py:65` 当日及未来工作日直接放行；已复现未来元旦被判交易日，违反“非交易日不启动 GUI”。
6. `execution/ths_account_runner.py:735` 在客户端已自行退出时仍先调用 UI 关闭并累计 close error；lifecycle 虽无残留仍报 `lifecycle_failed`，当前 10-26/27/28 连续出现。
7. `execution/ths_account_runner.py:799` 无完整资金账号时，订单幂等键取 OCR 显示文本哈希；OCR 前缀/噪声变化可使同一资金户跨重试获得不同身份，绕过单日一次台账。
8. `requirements.txt` 未声明 WebUI 必需的 `flask`、`ruamel.yaml`；新机 setup 后 WebUI 不保证可启动。
9. `webui/app.py:115` 起无认证/CSRF，`/mode` 可直接改 live；任意本机页面可在 WebUI 运行时发起跨站表单修改配置。
10. `scheduler/package_project.ps1:12` 未排除 `.venv-test`，当前该目录约 335.5 MB；输出不在 `runtime_data` 时，stage 目录位于源码树内，可能被再次打包/递归。
11. `notification/receipts.py:22` 仅对值做字符串正则，嵌套凭据映射不会递归清理；已复现密码进入回执正文。
12. `execution/ipo_page.py:138`、`:267` 批量 F8 只按代码/名称 `any()` 命中，不校验唯一行、数量或状态，弱于单笔核验。
13. Server酱免费版 5 条/日、邮件兜底关闭；MEMORY 已有额度耗尽导致关键回执丢失的真实故障。

### Medium

14. `scheduler/catchup.py:556` `phase=all` 对 login/subscribe/allotment 分别调用完整 workflow，三次启动/关闭客户端，与“每次调用只启动一次”规格冲突。
15. `execution/captcha_login.py:44` 持续保留 `runtime_data/ocr/debug_last_dialog.png`，当前 OCR 目录还有残留验证码图；验证码敏感画面长期落盘。
16. 32 位依赖图不满足 `pip check`；doctor 只测可导入，未测依赖一致性。
17. README/spec/operations 仍写“不自动填密码、不识别验证码”，与安全 spec 和实现冲突；08:25/08:30、5/7 个任务、测试数量、K4 状态等文档快照已漂移。
18. `hexin_login.py` 1777 行、`login.py` 1307 行、`test_ths_account_ui.py` 1162 行，违反 1000 行硬限制；legacy 路径与新路径并存。
19. 仓库仅 1 个 M1 提交，当前 83 个未跟踪项、20 个已修改项；核心 execution 代码几乎无版本历史。
20. `runtime_data` 约 84.5 MB、2786 个文件，含调试脚本、抓包、截图、安装包；无保留/清理策略。
21. 当前 `gui.lock`、`catchup.lock` 属已退出 PID 9856；下次运行可自愈，但全量测试会因此失败。测试不应依赖生产 runtime 无锁。
22. 14:17 新增的 `ths_client._buy_with_exchange` 交易所路由无专门测试，异常被静默吞掉；需真机验证上海/深圳/科创板申购路由，不能只凭 compileall。

## 优点

- 单一 32 位入口、动态账户发现、凭据 DPAPI、发送 URL/异常链脱敏方向正确。
- 申购默认双保险、订单台账 fail-closed、F8 不确定状态阻断重试，安全设计意识强。
- TaskState、原子替换、GUI/catch-up 锁、温和关闭与残留探测均有明确职责。
- 329 个隔离 mocks 测试通过，说明核心 happy path 与多数安全分支有回归保护。

## 风险与遗留

- 未触发真实 GUI、真实委托、计划任务启动或推送。
- 审查期间检测到另一任务并发修改 `execution/ths_account_runner.py`、`execution/ths_client.py`、`config/config.yaml`、`MEMORY.md`；本报告已按 14:17 后的最新快照复核。
- 当前 `execution.mode=live`，计划任务 Ready；Critical/High 未修复前继续无人值守存在误单、漏中签提示或配置被误改风险。
