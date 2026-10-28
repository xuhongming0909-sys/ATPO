# Mission 1015-m2-subscribe-flow — Spec

## 任务类型
实现（M2 第二阶段：申购流程 dry_run 串联）

## 目标
把「当日日历 → 账户过滤 → 申购指令 → 执行」链路打通。申购原理：买入申购代码（转债=发债代码@100 元，新股=申购代码@发行价）。本阶段默认 dry_run：生成指令并留痕，不真实下单。验证标准：`run.py subscribe` 对当日日历输出正确指令清单；live 需用户确认后单独执行。

## 范围
- 新建：`execution/subscribe.py`、`tests/test_subscribe.py`
- 改：`run.py`（subscribe 子命令）、`INDEX.md`
- 不碰：多账户切换（M3）、中签查询（M4）、管理界面（M3）

## 约束
- execution.mode=dry_run 时绝不调用真实下单接口
- live 下单必须：config mode=live 且命令行显式 `--live`
- 可转债顶格：深市（12xxxx/申购代码 0/3 开头）1 万张；沪市（11xxxx/申购代码 7 开头）1000 手
- 北交所标的按账户 bj_enabled 过滤；发行价未定的新股跳过并记录原因
- 权限清单为空=不过滤（以柜台为准）；非空则按 cb/sh_ipo/sz_ipo/cyb/kcb/bj 预过滤

## 对正式 spec 的影响
- specs/execution.md 增加申购指令生成规则
