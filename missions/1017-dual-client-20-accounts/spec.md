# Mission Spec

## 任务类型
实现并验证

## 目标
实现 E:\同花顺 与 E:\同花顺2 双实例、每实例最多 10 个动态账户的隔离自动化链路，并补齐项目可复制性、诊断、错误提示和扩展执行能力。

## 状态
2026-10-17 用户批准实施。代码、配置、正式 spec、测试和文档已同步；真实交易日 GUI 验收仍待执行，未在本任务中产生真实委托。

## 范围
- 双客户端进程、窗口、F12、jqktrader、账户上下文、截图和结果严格隔离。
- 账户按客户端菜单/下拉文本动态匹配 config；不按券商、账户 ID、资金账号或菜单行硬编码。
- boot-login、discover、preflight、subscribe、allotment 按 client_order 串行。
- 跨客户端资金账号哈希防重复；订单台账单账户单代码单日一次。
- 项目复制：统一路径、setup、doctor、结构化错误、DPAPI 换机提示、脱敏诊断。
- 不处理：两个客户端并发 GUI、密码/验证码自动绕过、权限猜测、WebUI 重做、真实委托。

## 输入
- config/config.yaml：账户元数据、两个客户端路径、GUI 参数、执行开关。
- config/secrets.yaml：资金账号与 DPAPI 密文，仅本机。
- E:\同花顺 与 E:\同花顺2 下的 hexin.exe/xiadan.exe。
- 64 位 Python 3.12 与项目 .venv32（32 位 Python 3.11）。

## 输出
- 每客户端独立发现、登录、预检、执行、截图和错误结果。
- 账户结果只含 client_id、account_id、显示名、资金账号哈希/脱敏值、状态和错误。
- runtime_data/diagnostics/client_discovery_*.json 只读账户清单。
- 全局订单台账阻断跨客户端重复账户。

## 错误处理
- 窗口/PID 归属不唯一：停止该客户端，不选第一个窗口。
- 密码/验证码/人工确认弹窗：停止该客户端剩余自动登录并报告 dialog_required。
- 未匹配/歧义/重复账户：config_missing / ambiguous / duplicate_account，不执行。
- 结果不明：unknown / submitted_unverified，禁止自动重试。
- 单客户端失败不影响另一个客户端；两个客户端绝不并发操作。

## 对正式 spec 的影响
已同步 specs/spec.md、specs/execution.md、specs/security.md、specs/portability.md、specs/requirements.md 和 INDEX.md。