# Mission 1015-m3-webui-accounts — Spec

## 任务类型
实现（M3 第一阶段：本地管理界面）

## 目标
用户不懂代码，唯一控制点是一个本地 Web 表单：账户增删改（券商/备注/普通·信用/北交所开关/权限/启用）、执行模式切换（dry_run/live）。写回 config.yaml 保留注释。验证标准：浏览器打开表单，新增账户保存后 config.yaml 真实更新；测试通过。

## 范围
- 新建：`webui/app.py`、`tests/test_webui.py`；run.py 加 `webui` 子命令
- AGENTS.md 根目录白名单需增加 `webui`（用户已通过「我只要一个表单」的明确需求批准）
- 不碰：多账户自动切换执行（M3 第二阶段）、中签查询（M4）

## 约束
- 表单不管密码（密码由同花顺客户端「记住密码」保管，符合安全宪章）
- 只监听 127.0.0.1，不对公网开放
- config.yaml 写回必须保留注释和结构（ruamel.yaml round-trip）
- TDD：flask test client，用临时 config 文件，不碰真实配置

## 对正式 spec 的影响
- specs/requirements.md M3 进度；INDEX.md 登记 webui
