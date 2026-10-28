# 多 AI Git 协作规则

适用范围：多个 AI 同时在本项目编码。目标是避免互相覆盖、互相回滚、把半成品推上 `main`。

## 1. 远程与分支

- 远程仓库：`git@github.com:xuhongming0909-sys/ATPO.git`
- `main` 是唯一集成分支；AI 不直接在 `main` 上开发。
- 每个 AI、每个任务一条分支：`ai/<agent>-<MMDD>-<topic>`。
- 分支名中的 `<agent>` 用 AI 名称缩写，例如 `codex`、`mimo`、`claude`。

## 2. 工作区隔离

推荐每个 AI 使用独立 git worktree：

```powershell
git fetch origin
git worktree add "C:\Users\93724\Desktop\自动打新-ai-<agent>" `
  -b ai/<agent>-1028-<topic> origin/main
```

规则：

- worktree 只用于编码和 mock 测试。
- 真实券商客户端、`runtime_data/`、`config/secrets.yaml` 只在主目录使用。
- 禁止多个 AI 共用同一工作目录修改同一批文件。
- 如果工具只能在主目录运行，必须先声明文件归属，再串行修改。

## 3. 文件归属

| 范围 | 归属规则 |
|---|---|
| `data_fetch/` | 日历/交易日模块负责人独占 |
| `execution/` | 券商客户端自动化模块负责人独占 |
| `notification/` | 推送与回执模块负责人独占 |
| `scheduler/` | 定时任务模块负责人独占 |
| `shared/` | 公共工具负责人独占；跨模块逻辑需协调 |
| `webui/` | 本机配置界面负责人独占 |
| `tests/` | 对应模块负责人修改自己的测试 |
| `AGENTS.md`、`INDEX.md`、`逻辑图.MD`、`specs/`、`config/config.yaml`、`MEMORY.md` | 热点文件，只允许协调 AI 修改 |

其他 AI 需要改热点文件时，只在自己的 mission 文档里写明建议，由协调 AI 统一合并。

## 4. 开工流程

每个非聊天任务先建 mission：

```text
missions/MMDD-short-name/spec.md
missions/MMDD-short-name/plan.md
```

开工前：

```powershell
git fetch origin
git status --short --branch
git rebase origin/main
```

## 5. 提交流程

- 一次提交只碰一个模块或一个明确主题。
- commit message 第一行带 mission 目录名。
- 提交前必须跑测试：

```powershell
.\.venv-test\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp runtime_data\pytest-tmp
```

- 测试失败不许提交，不许推 `main`。
- 推自己的分支：

```powershell
git push -u origin ai/<agent>-<MMDD>-<topic>
```

## 6. 合并流程

- 只有协调 AI 可以把分支合并回 `main`。
- 合并前重新基于最新 `main`：
  ```powershell
  git fetch origin
  git rebase origin/main
  ```
- rebase 出现在热点文件或共享模块的冲突：停止，交给协调 AI。
- 禁止 `git push --force` 到 `main`。
- 禁止 `git reset --hard`、`git clean`、删除别人的未提交改动。
- 合并后删除已合并分支和 worktree。

## 7. 安全边界

- `config/secrets.yaml`、`runtime_data/`、`.venv/`、`.venv32/`、`.venv-test/`、`python311-32/`、`.pytest_cache/` 永不进 git。
- 远程仓库必须保持私有。
- 任何实盘相关改动只能用 mock 测试验证，不能在并行开发分支触发真实委托。
