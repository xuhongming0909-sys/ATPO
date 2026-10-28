# Mission 1015-m1-calendar-bot — Plan

## 步骤
1. 探测东财新股/可转债日历真实接口与字段 → 记录到 specs/calendar.md
2. TDD 实现解析层（fixture 来自真实接口响应）
3. 实现 shared/config、notification/serverchan、scheduler/jobs、run.py
4. 本地三层验证：能导入 → 真实调用拿数据 → 推送真实送达
5. 服务器部署：bare git 仓库 + post-receive checkout + 定时任务
6. 服务器验证：手动触发一次 daily-report，确认推送送达
7. 更新 INDEX.md、MEMORY.md、mission 收尾

## 验证结果

- `pytest tests/ -q` → 5 passed（解析层 fixture 来自东财真实响应）
- `python run.py calendar --day 2026-10-16` → 真实返回中科转债（371175, AA+, 10 亿, 正股中科环保）
- `python run.py daily-report --day 2026-10-15/16` → 真实推送 2 条（华纬转债/中科转债），微信已送达
- Windows 任务计划 `AutoIPO-DailyReport`（工作日 08:25）注册成功；`Start-ScheduledTask` 手动触发后日志输出正常（runtime_data/daily-report.log）

## 结果

完成（按本地化架构调整后）。架构中途转向：放弃服务器部署（服务器内容已清理），调度从 cron 改为 Windows 任务计划程序。

## 风险与遗留

- 任务计划仅在本机开机且用户已登录时触发；错过 08:25 可手动 `python run.py daily-report` 补跑。
- 东财接口字段如变更会导致解析失败（已约定宁可抛错不静默），需关注运行日志。
- M2 阻塞项：需用户在安装好的同花顺客户端上完成一次平安账户登录验证。
- config/config.yaml 中 accounts[].permissions 待用户核实填写（不填也能跑，以柜台额度为准）。
