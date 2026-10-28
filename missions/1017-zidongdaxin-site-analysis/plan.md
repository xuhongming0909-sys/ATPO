# Mission Plan 模板

## 步骤
1. 解析域名、地址、证书、HTTP 跳转与服务器特征。
   验证：保存并核对 DNS/TLS/headers 真实输出。
2. 读取首页、robots、站点地图、公开静态资源和可见链接。
   验证：提取页面文案、表单、路由、脚本请求，确认每个结论有 URL/字段证据。
3. 对公开只读端点做最小请求，识别数据更新与业务链路。
   验证：不登录、不提交敏感数据；记录状态码、响应类型和必要字段。
4. 对照本地项目和公开搜索信息，区分事实与推断。
   验证：检查项目源文件映射，避免把猜测写成事实。
5. 汇总工作机制、数据流、安全与可靠性风险。
   验证：逐项标注证据来源和不确定处。

## 验证结果

### 1. 站点与部署

- `zidongdaxin.com`、`http://zidongdaxin.com` 均 301 到 `https://www.zidongdaxin.com/`。
- A 记录：`101.43.73.101`；无 CNAME/AAAA。RDAP：2017-02-13 注册，2027-02-13 到期；Registrar 为 Alibaba Cloud；NS 为 `dns15.hichina.com` / `dns16.hichina.com`。
- TLS：Let's Encrypt，SAN 覆盖 apex/www；2026-09-17 至 2026-12-16；本次协商 TLS 1.2。
- Web：Nginx + ThinkPHP 3.2.3。404 错误页直接暴露 `/data/wwwroot/zddx/` 与框架版本。
- 首页备案展示：`沪ICP备17004639号-2`。
- `robots.txt` 返回 `User-agent: *` / `Disallow: /`；`sitemap.xml` 404。

### 2. 公开页面与业务入口

- 首页是微信/手机优先的营销落地页，文案为“定时定点、安全便捷、立即开启”，并提供新股日历、可转债日历、公众号二维码。
- 首页加载 `/api/hitNewPost/getHitCount`。2026-10-17 12:15 CST 快照：`all_number=1409103`（累计申购次数）、`lucky_number=15918`（累计中签），比例约 `1.1297%`。这是站点展示值，无法从公开接口独立审计真实性。
- “立即开启” `goNext()`：
  1. GET `/api/wechatLog/trigger?type=click_start_hitnew` 记录点击；
  2. GET `/api/broker/getdata`；
  3. `data.have=1` 去 `/userCenter/index`，否则去 `/broker/index`。
- 未登录访问 `/broker/index`、`/userCenter/index` 均 302 到 `/home/index/phoneLogin`。
- 手机登录页流程：
  1. GET `/api/user/sendVerifyHasPhone?phone=...` 发短信验证码；
  2. POST `/api/user/phoneLoginPost`，字段 `phone`、`code`；
  3. 响应 `account_count > 0` 去 `/home/userCenter/index`，否则去 `/home/index/index`（推断为首次添加券商账户）。
- 未登录 `/api/broker/getdata` 返回 `secret:null, have:0`。未调用带副作用的 `/api/wechatLog/trigger`，未提交手机号/验证码/账户信息。

### 3. 数据与自动化链路

- 新股公开接口：`/api/calendar/grtList`（页面实际调用 `/api/Calendar/grtList`）。返回 `today/today_status/newData/newData_status`。
- 新股字段含申购代码、申购日、上市/配号/缴款/确认日期、发行量、网上发行量、发行价、市盈率、个人申购上限、募资额、中签率、中签号。每批 20 条。
- 新股 `updated_at` 均为 `2026-10-17 08:00:01`，部分 `created_at` 为 `08:00:01/02`；证据支持后端每日约 08:00 批量刷新，但调度实现不可见。
- 可转债公开接口：`/api/Calendar/bondList`。字段含正股价 `zgj`、转股价 `to_share_money`、转股价值 `zgjz`、申购代码、申购日、顶格数量、概率等，每批 20 条。
- 可转债页面同时出现两条策略证据：页面标题写“转股价值大于 95 则自动申购”，括号又写“目前全申购”；模板只在 `zgjz > 95` 时显示“自动申购”标签。当前实际策略存在文案/实现不一致，不能断言真实下单条件。
- 微信 JS-SDK 用于分享；页面引导关注公众号接收打新信息。CSS/路由还出现 Broker、Account、Renew、UserCenter、Message、邀请码、绑定手机、暂停/开启、会员、添加账户、退出等结构，推断产品包含账户绑定、自动申购开关、消息记录、会员/续费和多账户管理。
- 直接证据只能覆盖公开日历、登录入口和路由。**实际券商下单方式、账户密码存储、任务调度、失败重试、中签/缴款闭环必须登录后才可见，本次未验证。**

### 4. 架构推断

推断的主链路：

`微信公众号/落地页 → 手机验证码注册登录 → 绑定券商账户 → 后端日历批量更新 → 定时自动申购 → 消息/公众号通知 → 用户中心记录/续费/开关`

其中“绑定券商账户”“后端直接执行申购”是基于页面文案、Broker/Account 路由和产品定位的高可信推断，不是后端实证。

### 5. 安全观察

- HTTPS 有效，但首页未见 HSTS、CSP、X-Frame-Options、X-Content-Type-Options、Referrer-Policy。
- `thinksession` Cookie 仅设 `path=/`，未见 `Secure`、`HttpOnly`、`SameSite`。
- JSON API 返回 `Access-Control-Allow-Origin: *`。
- 发验证码使用 GET，手机号可能进入 URL/代理/服务器访问日志。
- 404 页泄露绝对路径与 ThinkPHP 版本。
- `common.js` 内嵌 RSA 公钥，暗示客户端可能加密敏感字段；公钥公开本身正常，但不能证明传输、落库和密钥管理安全。
- 对涉及券商资金账号/交易密码的服务，上述暴露面应按高风险处理。

## 结果

完成。已解释公开可见的工作机制，并明确区分直接证据与推断。未登录、未提交表单、未触发任何申购或交易动作。

## 风险与遗留

- 实际交易执行端和凭据存储不可见；若要审计，需要产品方文档、代码或用户授权后的只读账户检查。
- 可转债“>95 自动申购”与“目前全申购”冲突，需以真实成交前策略或产品方说明为准。
- 统计数字为站点自报，不能视为经过审计的真实累计量。
- `ThinkPHP 3.2.3`、会话 Cookie、CORS、错误页泄露和 GET 验证码接口需要独立安全评估；本次未做漏洞扫描或利用验证。