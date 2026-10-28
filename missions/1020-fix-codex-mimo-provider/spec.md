# Mission: 修复 Codex 线程 mimo provider 缺失

- 任务类型: 环境修复
- 目标: 让线程 01a14de8-8cf9-74b1-a561-96bff6dbb30f 恢复可加载（报错 Model provider `mimo` not found）
- 范围: C:\Users\93724\.codex\config.toml、cc-switch-model-catalog.json
- 约束: 不影响当前默认 provider（custom/kimi）；不泄露凭据到 git
- 对正式 spec 的影响: 无（不改本项目 specs）
