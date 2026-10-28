# Portability 规格（Windows 本机项目复制）

## 目标

把项目移动到另一台 Windows 电脑后，可通过统一初始化、诊断、打包入口工作。目标是“可复制、可定位、可修复”，不是免安装单 EXE。

## 当前模式

- 唯一模式：单同花顺切户（`execution.ths_account_switch`）；双客户端模式已于 2026-10-21 移除。
- 新模式只配置同花顺登录账户显示名和客户端路径；资金账户由 xiadan 动态发现，不保存完整资金账号。

## 打包规则

生成干净压缩包：

```powershell
powershell -ExecutionPolicy Bypass -File scheduler\package_project.ps1
```

可选指定项目根目录和输出文件：

```powershell
powershell -ExecutionPolicy Bypass -File scheduler\package_project.ps1 `
  -ProjectRoot "C:\Users\93724\Desktop\自动打新" `
  -OutputPath "runtime_data\package\auto-ipo-clean.zip"
```

强制排除并在打包前后复核：

- `config/secrets.yaml`
- `runtime_data/`
- `.venv32/`
- `__pycache__/`
- `.pytest_cache/`
- `.git/`
- `screenshots/` 及文件名含 `screenshot/截图` 的图片

脚本不得跟随符号链接/目录联接；输出、临时目录和删除/移动目标必须位于项目根目录内。发现敏感文件或截图进入暂存区/zip 时立即失败并清理，不生成可交付包。

## 运行边界

- 仅支持 Windows 交互桌面；同花顺客户端是外部依赖。
- `.venv32/`、`runtime_data/`、`config/secrets.yaml` 不随项目包复制，在目标电脑初始化或重新录入。
- DPAPI 凭据绑定 Windows 用户。换电脑/换用户后不得沿用旧密文，必须重新加密录入。
- 截图、运行结果、日志、订单台账均留在本机 `runtime_data/`，禁止作为项目包内容复制。

## 路径规则

- 项目根目录由 `shared/paths.py` 统一解析。
- 配置相对路径基于项目根目录；绝对路径、`%ENV%` 原样展开。
- 运行时目录统一为 `runtime_data/`，启动时自动创建 logs、screenshots、results、order_ledger、errors、diagnostics、boot_login。
- 代码不得散落 `Path(__file__).parent.parent / "runtime_data"`。
- 新模式客户端路径只放 `config/config.yaml → execution.ths_account_switch`；回滚模式路径放 `execution.clients`。

## 依赖规则

- 64 位通用环境：`requirements.txt`，负责日历、通知、CLI、测试。
- 32 位执行环境：`.venv32` + `execution/requirements32.txt`，负责 pywinauto、pywin32、jqktrader、pandas。
- `scheduler/setup.ps1` 统一创建/修复两个环境，安装顺序固定并输出失败原因。
- `scheduler/run64.cmd` 优先使用 `py -3.12`，不存在时回退 `python`。
- `scheduler/run32.cmd` 只使用项目内 `.venv32`。

## 诊断规则

`python run.py doctor` 单模式检查同花顺切户配置、DPAPI 与账户元数据。

共同检查：

- 项目根目录、运行时目录是否可写。
- Python 版本/位数、64/32 位依赖是否可导入。
- `config.yaml`、`secrets.yaml` 是否存在，配置是否可解析。
- `.venv32` 是否存在并可执行。

`ths_account_switch` 额外检查：

- 同花顺显示名非空且唯一。
- 同花顺登录账户总数为 1 到 10。
- `hexin_path`、`xiadan_path` 指向真实 exe。
- `ths_account_secrets.<username>.password_enc` 为可选项；缺失或当前用户无法解密只输出明确 warning，不输出密文。
- 不要求 `accounts_secrets`、完整资金账号或 WebUI。



- 账户 ID 唯一、启用账户 secrets 元数据、资金账号唯一。
- 每个 `execution.clients` 的 hexin/xiadan 路径存在且不重复。
- 旧 DPAPI 密文可由当前用户解密。

错误输出统一包含 `code`、`message`、`hint`、`path/key`、`next_action`；非阻断提示进入 `warnings`。禁止只抛“失败”。

## 复制后启动流程

```text
生成干净 zip 并核对排除清单
  → 在目标电脑解压到短路径
  → powershell -ExecutionPolicy Bypass -File scheduler\setup.ps1
  → 修改 config/config.yaml 客户端路径与 THS 显示名
  → 复制 config/secrets.example.yaml 为 config/secrets.yaml
  → 按需重新录入 DPAPI 密码密文与 SendKey
  → python run.py doctor
  → 交易日执行 ths-cycle 登录/申购/中签
```

## 可移植性验收

- 打包产物不含 `config/secrets.yaml`、`runtime_data`、`.venv32`、缓存、git、截图或密文。
- 包内保留 `config/secrets.example.yaml`，目标电脑能据此重建敏感配置。
- 在非开发目录解压后 `python run.py doctor` 能给出完整状态。
- 缺失 Python、依赖、配置、同花顺、可写目录时，有明确错误码和修复命令。
- 新模式不泄露完整资金账号、密码、SendKey；DPAPI 换机失败只给 warning 并要求重新录入。
