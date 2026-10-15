# Spec 总图 — 自动打新系统

本文件是项目级地图与索引，只管概览、地图、索引、全局规则摘要；详细需求进各子 spec。

## 子 Spec 索引

| 文件 | 内容 |
|---|---|
| `specs/requirements.md` | 需求与总体架构（业务目标、权限前置、时间节点、架构、里程碑） |
| `specs/security.md` | 安全规格（凭据存储、实盘开关、留痕要求）— 待建 |
| `specs/calendar.md` | 打新日历数据源与字段规格 | ✅ |
| `specs/notification.md` | 通知通道与消息格式规格 | ✅ |

## 全局规则摘要

- 形态：服务器（大脑）+ 本机 Windows 执行端（手），券商密码永不上服务器。
- 券商接入：同花顺 PC 客户端 + easytrader，首接平安证券。
- 策略：新股/可转债全部申购。
- 通知：Server酱为主，关键消息（中签缴款）需兜底通道。
- 默认 `execution.mode: dry_run`，实盘需显式开启。
- 工作规则见 `AGENTS.md`，文件索引见 `INDEX.md`。
