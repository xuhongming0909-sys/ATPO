# 自动打新系统

可转债 + 新股（沪深主板/创业板/科创板/北交所）自动申购与中签提醒系统，自用。

## 架构一句话

**服务器（腾讯云 Ubuntu）做大脑**：打新日历、调度、通知推送、状态存储；
**本机 Windows 做手**：券商客户端自动化申购/中签查询，券商密码只存本机。

## 当前里程碑

- **M1（进行中）**：每日打新提醒机器人（服务器端，纯日历 + Server酱推送，不碰券商）
- M2：平安证券单账户自动申购全链路（本机执行端）
- M3：华宝/中信建投接入 + 多账户调度
- M4：中签自动查询 + 缴款提醒闭环

## 快速开始（M1 落地后的目标接口）

```bash
pip install -r requirements.txt
python run.py calendar        # 手动拉一次今日打新日历
python run.py notify-test     # 发一条 Server酱 测试消息
```

Server酱 SendKey 填入 `config/secrets.yaml`（模板见 `config/secrets.example.yaml`）。

## 文档导航

- 规则：`AGENTS.md`
- 文件索引：`INDEX.md`
- 需求与架构：`specs/requirements.md`
- 需求总图：`specs/spec.md`
- 交接记忆：`MEMORY.md`
