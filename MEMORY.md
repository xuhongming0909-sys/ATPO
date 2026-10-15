# Memory

**Retention**: 最多 50 条，超出删最旧。
**只记录**：决策、有意义的动作、验证结果、值得记住的失败、下一步。
**禁止**：倾倒完整对话。

## Entries

### 2026-10-15 | 通道与服务器验证通过 + 纯服务器方案评估

- **Verified**: Server酱推送实测成功（pushid 61781931，errno 0）；SendKey 已存 config/secrets.yaml（git 忽略）。
- **Verified**: SSH 到 43.139.35.190 成功（paramiko 密码认证，本机无 sshpass）。服务器状态：运行 140 天，alpha-monitor active，磁盘余 25G，内存余 2.5G，Python 3.12.3。SSH 凭据已存 secrets.yaml。
- **Decision**: 纯服务器方案存在——S1 券商官方预约打新（平安/中信建投 APP 内有智能打新，券商端执行，零机器开机）；S2 Windows 云服务器跑 easytrader（月费百元级）。推荐 S1 为主路径，execution/ 降级为可选增强。待用户拍板 S1 vs S2。
- **Next**: M1 每日打新提醒机器人开工（两条路径通用）；用户需在平安证券 APP 确认可转债权限 + 体验预约打新功能。

### 2026-10-15 | 项目立项：需求与架构 v2 定稿

- **Decision**: 形态定为「服务器+本机执行端」混合架构。服务器（腾讯云 43.139.35.190 Ubuntu）跑日历/调度/通知；券商客户端自动化只在本机 Windows 跑，密码不上服务器。
- **Decision**: 首个接入券商 = 平安证券（走同花顺 PC 客户端 + easytrader）。
- **Decision**: 通知通道 = Server酱（SendKey 待用户注册后填 config/secrets.yaml）。
- **Decision**: 新股策略 = 全部申购（可转债同样全打），黑名单机制后续再加。
- **Decision**: 项目规则借鉴 Alpha monitor：git 同步工作流、mission 制度、AI-SUMMARY、根目录清洁、1000 行文件上限、TDD、职责分离、配置集中、安全宪章（AGENTS.md Constitution §9）。
- **Action**: 建立项目骨架（AGENTS/INDEX/MEMORY/README/specs/config/templates），git init。
- **Next**: M1 每日打新提醒机器人（data_fetch 日历抓取 + notification Server酱 + scheduler 定时），部署到服务器 systemd。
- **Blocker**: 需用户提供 Server酱 SendKey；服务器 SSH 凭据需用户提供或授权复用。
