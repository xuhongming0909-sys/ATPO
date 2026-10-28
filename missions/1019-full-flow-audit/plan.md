# Mission Plan

## 步骤
1. 读取 `AGENTS.md`、`INDEX.md`、`README.md`、`specs/spec.md`、`specs/requirements.md`、`specs/execution.md`、`specs/operations.md`、`specs/security.md`、`config/config.yaml`。
   - 验证：架构、live/dry-run、账号脱敏、GUI 生命周期规则与代码入口一致。
2. 运行 Python 3.12 全量测试、编译检查、`run.py doctor`，保留失败原文。
   - 验证：测试结果、诊断结果、版本、路径和 32/64 位环境。
3. 静态审查核心链路：日历 -> 调度 -> 账户发现/登录 -> 申购 -> 订单台账 -> 中签 -> 回执 -> catch-up。
   - 验证：每个阶段的输入、输出、异常、幂等、权限、脱敏和落盘位置。
4. 读取真实运行时状态和计划任务，不做真实委托。
   - 验证：`task_state.json`、生命周期记录、计划任务、客户端进程/路径。
5. 运行安全 GUI 全流程：`discover`、`preflight`、`ths-cycle --phase login`、`subscribe --day 2026-10-19` 默认 dry-run、`allotment` 只读查询。
   - 验证：客户端启动/登录/账户切换/申购表单/订单台账/中签查询/温和关闭均有证据；不产生真实委托。
6. 汇总漏洞等级、根因、影响、证据、修复顺序和回滚边界。

## 验证结果
待执行。

## 结果
待执行。

## 风险与遗留
- 同花顺 GUI 版本、窗口布局、OCR、网络和账户状态会改变结果。
- `config execution.mode=live` 存在误触发风险；本任务不传 `--live`。
- 真实交易日申购窗口和账户权限可能限制 dry-run 数据。