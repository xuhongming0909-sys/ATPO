# Mission 1015-m1-calendar-bot — Spec

## 任务类型
实现

## 目标
M1 每日打新提醒机器人：每个交易日早上自动抓取当日可申购的新股/可转债，通过 Server酱推送到微信。验证标准：本地 `python run.py daily-report` 真实抓取 + 真实推送成功；服务器部署后定时任务自动触发。

## 范围
- 新建：`shared/config.py`、`data_fetch/calendar.py`、`notification/serverchan.py`、`scheduler/jobs.py`、`run.py`、`requirements.txt`、`tests/`
- 部署：服务器 bare git 仓库 + systemd timer（或 cron），systemd 服务名 `auto-ipo`
- 不碰：券商客户端自动化（execution/，M2 再说）、Web UI、数据库

## 约束
- 遵守 AGENTS.md：职责分离、配置集中（config.yaml）、AI-SUMMARY、文件 <1000 行、TDD
- 推送消息中不出现任何敏感信息
- 真实数据验证（Truth First）：必须用东财真实接口返回验证解析正确
- 与服务器已有 alpha-monitor 服务零冲突（独立端口/目录/定时器）

## 对正式 spec 的影响
- 更新 `specs/requirements.md`（权限策略已定，本次已完成）
- 新建 `specs/calendar.md`（日历数据源与字段规格）、`specs/notification.md`（通知规格）
