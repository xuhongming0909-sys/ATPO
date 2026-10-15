# INDEX — 项目架构与文件索引

> 新建/移动/删除文件后必须更新本文件。文档总量超 500 行时拆分。

## 1. 架构总览

```
腾讯云服务器 (43.139.35.190, Ubuntu, systemd: auto-ipo)
  ├─ scheduler/    定时编排：08:30 拉日历 → 09:35 触发申购 → T+1 21:00 查中签
  ├─ data_fetch/   打新日历抓取（东方财富/集思录）
  ├─ notification/ Server酱推送（申购日报/中签提醒/异常告警）
  └─ shared/       配置、时间、日志、运行时状态

本机 Windows 执行端
  └─ execution/    券商客户端自动化（easytrader + 同花顺），密码 DPAPI 加密存储
       ↑↓ 执行端主动轮询服务器任务 API，结果回报（仅外呼，无入站端口）
```

## 2. 目录职责

| 目录 | 职责 | 部署位置 |
|---|---|---|
| `data_fetch/` | 打新日历抓取 + 规范化 | 服务器 |
| `scheduler/` | 定时任务编排（对齐交易所日历） | 服务器 |
| `execution/` | 券商客户端自动化申购/查询 | 仅本机 |
| `notification/` | 推送通道封装 | 服务器 |
| `shared/` | 配置加载、交易日判断、日志 | 两端共用 |
| `config/` | config.yaml（非敏感）/ secrets.yaml（git 忽略） | 两端 |
| `deploy/` | systemd、同步脚本 | 服务器 |
| `specs/` | 正式需求文档 | — |
| `missions/` | 任务档案（保留最近 30 个） | — |
| `templates/` | 文档模板（用户所有，AI 不可改） | — |
| `tests/` | 测试 | — |
| `runtime_data/` | 日志、截图、运行状态（git 忽略） | 两端 |
| `archive/` | 归档 | — |

## 3. 文件摘要索引（AI-SUMMARY 登记处）

| 文件 | 一句话职责 |
|---|---|
| `run.py` | CLI 统一入口（calendar / notify-test / subscribe / check-allotment） |

（随代码落地持续登记）

## 4. 服务器档案

- 主机：43.139.35.190（腾讯云 Ubuntu）
- 应用目录：`/home/ubuntu/auto-ipo`
- 服务：`auto-ipo`（systemd）
- 连接凭据：`config/secrets.yaml`（git 忽略，本地保管）
