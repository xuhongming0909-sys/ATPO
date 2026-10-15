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
（实施完成后填写）

## 结果
（实施完成后填写）

## 风险与遗留
（实施完成后填写）
