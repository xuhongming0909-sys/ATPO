# Mission 1015-m3-webui-accounts — Plan

## 步骤
1. 装 flask + ruamel.yaml
2. TDD：4 个 webui 测试（列表渲染/新增账户/取消勾选即停用/模式切换）
3. 实现 webui/app.py（127.0.0.1:8321）
4. run.py 接入 webui 子命令，浏览器实测

## 验证结果
- pytest 20 passed（含 webui 4 项）
- 浏览器实测：页面渲染正常，显示执行模式 live 徽标、平安证券账户行、新增账户行、保存按钮
- 修复：Jinja2 不支持 loop.parent（改用 set outer_i）；run.py 局部 import 遮蔽问题

## 结果
完成（M3 第一阶段）。

## 风险与遗留
- Flask 开发服务器仅自用监听 127.0.0.1，可接受；不对外开放。
- 表单 v2（同日追加）：删除按钮、自动增行、ID 留空自动取资金账号、北交所并入权限、券商候选 7 家。
- M3 第二阶段（多账户 xiadan 内自动切换执行）未开始；execution/login.py 自动登录待真实凭据实测。
