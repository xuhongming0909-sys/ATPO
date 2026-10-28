# Mission Spec — M5 开机自动登录同花顺

## 任务类型
实现

## 目标
开机（用户登录）且网络就绪后，自动打开同花顺主客户端并经 F12 拉起 xiadan，
把 config 中前 10 个启用账户逐户切换登录一遍，使交易页面随时可切这 10 个账户；
完成推送 Server酱 就绪户数。验证标准：`run.py boot-login` 全链路执行 + pytest 通过。

## 范围
- 新增 `execution/boot_login.py`（等网络 + 逐户登录编排 + 留痕 + 推送）
- 新增 `run.py boot-login` 子命令
- 新增 `tests/test_boot_login.py`（全部用桩，不碰真实客户端）
- `config/config.yaml` 新增 `boot_login:` 段（max_accounts / probe_url / network_timeout_s）
- 注册 Windows 计划任务 `AutoIPO-BootLogin`（ONLOGON 触发，延迟 1 分钟）
- 更新 specs/execution.md、specs/spec.md、INDEX.md、MEMORY.md

不做：hexin 主客户端右上角账户密码录入自动化（登录框自动化已废弃归档，
本任务复用「已登录账户顶栏切换」机制，无需密码）；不动 subscribe/allotment 主流程。

## 约束
- 安全红线：不记录/不推送资金账号与密码；截图留痕到 runtime_data/；单户失败不阻塞其余
- 遵守 AGENTS.md：TDD 三环、配置集中（新参数进 config.yaml）、AI-SUMMARY 注释、执行端 32 位 venv
- 用户补充约束：开机后不自动联网，必须等网络就绪再执行（脚本内轮询探活，而非开机瞬间硬跑）

## 对正式 spec 的影响
- `specs/execution.md`：登录/换户模式下新增「开机自动登录」小节
- `specs/spec.md`：系统逻辑图新增 AutoIPO-BootLogin 任务行
