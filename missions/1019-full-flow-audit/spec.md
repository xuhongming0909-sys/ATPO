# Mission Spec

## 任务类型
审查 / 分析

## 目标
审计“自动打新”当前工作树的漏洞、逻辑缺口和落位偏差，并在真实同花顺 GUI 环境中执行不产生真实委托的全流程验收，给出可复现证据。

## 范围
- `shared/`、`data_fetch/`、`scheduler/`、`execution/`、`notification/`、`webui/`、`run.py`、`config/config.yaml`
- 只读静态审查、测试、诊断、真实 GUI 生命周期/登录/申购 dry-run/中签查询链路
- 不提交真实申购委托；不修改 `AGENTS.md`、`templates/`；不在本任务中扩大产品需求

## 约束
- `execution.mode=live` 只是配置状态，真实委托仍必须显式 `--live` 且经过用户确认。
- 不读取或输出 `config/secrets.yaml` 中的密码、DPAPI 密文、SendKey、token。
- 不强杀同花顺进程；GUI 失败保留截图、日志和错误码。
- 发现 P0/P1 后先记录，不在审查阶段静默修改代码。
- 测试必须使用 mock；真实 GUI 只做只读/安全阶段。

## 对正式 spec 的影响
当前只做审查和验收，不改变正式需求。若审查确认需求与实现不一致，先在本 mission 记录，另行更新 `specs/*.md` 后再修代码。