# Mission 1015-m2-subscribe-flow — Plan

## 步骤
1. TDD：6 个测试覆盖转债深市/沪市顶格、新股发行价与上限、无价跳过、北交所开关、权限预过滤
2. 实现 execution/subscribe.py（prepare_orders + execute 双模式）
3. run.py 接入 subscribe 子命令（--live 与 config 双确认）
4. 真实 dry_run 验证

## 验证结果
- pytest 13 passed（全部）
- `run.py subscribe --day 2026-10-16` 输出：`dry_run 中科转债（371175）10000张 @100.0`（平安账户，权限空=不过滤）

## 结果
完成（dry_run 链路打通）。

## 风险与遗留
- live 实盘首单待用户确认：需 config execution.mode=live + --live 执行；建议首单选可转债（不冻资、零风险）。
- live 路径的用户回报读取（委托确认）与截图留痕在实盘首单时一并验证。
- 10:00 定时申购任务计划在 live 验证通过后注册。
