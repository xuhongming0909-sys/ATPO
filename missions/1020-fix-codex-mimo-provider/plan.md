# Plan

1. [x] 定位根因：旧线程 session 记录 model_provider_id=mimo；今日 cc-switch 切 Kimi 重写 config.toml，mimo provider 被移除
2. [x] 从 cc-switch.db 找回 mimo codex 配置：base_url=https://token-plan-cn.xiaomimimo.com/v1，wire_api=responses，token=tp-c685...
3. [x] config.toml 追加 [model_providers.mimo]（备份 .bak-mimo-fix-20261020）
4. [x] catalog 补 mimo-v2.6-pro 条目（slug/display_name，priority=999）
5. [x] 验证：tomllib 解析通过（providers=custom,mimo）；catalog JSON 解析通过（5 个模型）
- 结果: 已修复，待用户在 Codex 重新打开线程确认
- 风险: cc-switch 下次切换可能再次重写 config.toml 覆盖 mimo 块
