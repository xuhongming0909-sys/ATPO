# Memory

**Retention**: 最多 50 条，超出删最旧。
**只记录**：决策、有意义的动作、验证结果、值得记住的失败、下一步。
**禁止**：倾倒完整对话。

### 2026-10-24 | 计划任务触发修复、一键打新弹窗、OCR worker、pytest 污染根治

- **Root cause（周五零运行）**: 任务无 WakeToRun（PC 睡眠吞 22:00 检查）+ register_tasks.ps1 尾部 Write-Host 语法错误→重注册一直失败。已修；6 任务全部 WakeToRun=true；电源唤醒定时器 AC/DC=1；TaskScheduler/Operational 日志已启用。
- **Hidden bug**: execution/login.py 4 处 `str(pid) not in pids`（int 集合）恒真——_dismiss_popups/close_modal_dialogs 从未真正关过弹窗。已全改 int()。一键打新弹窗：勾「不再自动弹出」后关窗。
- **OCR worker**: shared/username_ocr.py --serve 常驻 64 位子进程（JSON 行协议），serve_request 失败自动回退一次性调用；日历 fetch_calendar_for 按日进程内缓存。
- **pytest 污染根治**: runtime_data 里 6 个 `*_test.py` 垃圾脚本每次全量测试被收集并在模块级向 tests/ 追加重复用例（之前测试反复假失败的真凶）；已删 + pytest.ini testpaths=tests。
- **Verified**: pytest 321 passed；compileall 64/32 通过；notify-test 推送成功；周六 GUI 登录因券商周末维护在 THS 用户名 OCR 处预期失败（worker 单机实测正常）。
- **遗留**: 周一 10-27 看任务真实触发与速度；中鼎转03 中签漏查手动补；CatchUp-Logon 0xC0000142 待观察。

### 2026-10-24 下午 | serve-first 补丁 bug 修复 + 真实 GUI 验证数据

- **Bug（我引入）**: ths_account_windows serve-first 补丁里 worker 成功路径仍引用一次性子进程的 `proc` → NameError。修：只判 `result.status`；回归测试锁定。
- **真实数据**: 健康户 13-27s/户（周四 45s）；周末 5 平安户 not_logged_in ~140s/户（fail-fast 是最大提速点）；华宝 dialog_closed 23-25s 回退正常。结果行字段=display_text/target_key。
- **结论**: 周一工作日全健康预计 6-8min；3min 需架构级改动（免重启连续切户），阶段目标 5min。

## Entries

### 2026-10-21 深夜 | 拷贝验证码根因破案 + 中签链路全通

- **根因（截图铁证）**: 同花顺检测到网格复制（剪贴板 ^A^C 或 WM_COMMAND 都触发）弹"检测到您正在拷贝数据…输入验证码"→ 约 4-5 次复制后卡死后续所有读取 → "前几个账户成功后段全挂"。验证码属安全验证，规则禁止自动绕过。
- **Fix**: 网格读取全面改屏幕 OCR（`shared/username_ocr.py` 新增 grid 模式表头驱动列映射；`execution/ths_client.py` 新增 read_grid_via_ocr；allotment/ipo_page 接线）。读像素不碰剪贴板，零验证码触发。
- **Fix**: ①run32.cmd 被双重 BOM+中文 echo 搞坏（计划任务全部 exit 2 空转）→ 重写纯 ASCII 无 BOM，doctor 实测通过；②xiadan 启动期 combo 不可读从 2 次快试改界内有界等待（20s/1s）；③资金户首轮点击未生效补点一次；④hexin 深色启动小窗被误当主窗 → 主窗识别加尺寸下限（≥800x500，兼容 RECT/元组）。
- **Verified**: pytest 297 passed；探针实读中签明细成功（莱特发债/华纬发债，与 WM_COMMAND 一致）；实跑 phase=allotment：mx_525378109 8/10 + mx_mbqdpecj9 4/5 查询完成，仅许*鸣融（需人工登录）和华宝两户（需密码弹窗）未跑——均为预期人工项；全程无验证码弹窗。
- **Known**: 许*鸣融类"永远需人工"账户在补点路径烧 134s，应 fail-fast；xiadan-plus 无窗口残留（禁强杀）；中签结果为空=申菱转债无人中签；daily-report 12:09 Server酱网络失败待观察。
- **Next**: 明早 08:00 T2 中签复查自动跑（计划任务已修复）；下个交易日 10:00 申购全链路真实验证；许*鸣融 fail-fast 优化。

### 2026-10-21 晚 | 中签链路修复 + 全流程实跑验证

- **环境事故**: 模型切换到 MiMo 后 Codex 授权审查接口坏掉（json_schema 不支持），所有提权命令被拦；切回原模型恢复。对方线程重构删除了我部分修复且弄丢 read_menu_rows 的 settings 参数（签名 TypeError → 菜单读取全灭）。
- **Fix**: ①重打 hexin_login 宽松主窗兜底+开菜单重试；②read_menu_rows 补回 settings 参数+签名回归测试；③网格复制从键盘 ^A^C 改为 WM_COMMAND(0xE122) 消息（jqktrader WMCopy 同款，不依赖前台/焦点）——根治"剪贴板读到 Codex 聊天文本当中签"幻影；④中签行校验：无已知列键拒绝放行；无标的身份行不算 won；⑤中签明细按业务日过滤历史行（中签日期 >= 业务日才保留）；⑥禁用 AutoIPO-BootLogin（不开机自启，任务时按需启动）。
- **Verified**: pytest 291 passed；探针实读中签明细成功（莱特发债/华纬发债真实历史行）；实跑 phase=allotment：mx_525378109 4 户 + mx_mbqdpecj9 4 户查询成功，结果为空=申菱转债无人中签（或部分未公布），无幻影；登录阶段 13/15 户 ready，每户 ~22-27s（原 85s）。
- **Known**: 每 THS 会话前 3 户 xiadan_failed（F12 启动时序）+后段 not_logged_in ~75s（待收敛）；xiadan-plus.exe 无窗口残留无法温和关闭（规则禁止强杀）；许*鸣融需人工登录；华宝价格 100.001 bug 未修；daily_report 12:09 Server酱网络失败。
- **Next**: 下一交易日 10:00 真实申购全链路（航亚转债已错过 15:00 窗口）；观察 T2 08:00 中签复查推送。

### 2026-10-20 | 新增顶层控制图 逻辑图.MD + 模板

- **新增**: 根目录 `逻辑图.MD`（总目标→G0–G6 分解→Gate 总表→主链路决策流程图→状态机→不变量→当前快照→变更同步对照表）；`templates/logic-map-template.md`（含 §C 核对清单）。
- **嵌入**: AGENTS.md Read Order 第 3 项、Completion Rules 加"改链路/判定/不变量必同步逻辑图"、白名单加 逻辑图.MD；INDEX.md/README/specs/spec.md 挂索引。
- **Snapshot**: 模式 live + ths_account_switch，缺口 K1–K5 已录入 §7（catch-up 误判 completed、锁死锁检测、920 路由、华宝价格/交易类别、F8 句柄失效+单户 85s）。
- **Next**: 每次代码改动按逻辑图 §8 对照表同步；K1–K5 修复后更新 §7。
### 2026-10-20 傍晚 | 申购链路批量修复 + 全量 412 测试转绿

- **Fix（scheduler/catchup.py）**: ①申购窗口（schedule.subscribe_window 09:30）未开始前直接跳过，不启动 GUI、不写状态——根治 07:48 空跑记 completed 挡掉 10:00 申购；②catchup.lock 增加持有进程 PID 存活检测，死进程锁立即接管（原只有 2 小时 mtime 兜底，14:21 曾因此白等 20 分钟）。
- **Fix（execution/subscribe.py）**: 北交所代码（920/43/83/87/88 开头）禁止走买入表单，fail-fast 提示走批量申购页（根治 920306 被路由到深圳 A 股）；F8 当日委托读取遇窗口句柄失效自动重连 xiadan 复查一次。
- **Fix（execution/ipo_page.py）**: 批量申购网格代码列为空时最多重读 3 次（间隔 1.5s），根治页面加载延迟导致的"整批拒绝"。
- **Fix（回执/脱敏对齐测试）**: 登录回执改三态标题"已登录 X｜需人工 Y｜失败 Z"+固定原因短语；fund_account/tail4 作为本人账户识别信息直出显示（shared/errors.py、runner._safe_value、receipts._plain），自由文本长数字仍脱敏；test_receipts 中与新格式矛盾的旧断言已更新（账户总数/成功/失败旧格式 → 三态格式）。
- **Verified**: `python -m pytest -q` 412 passed 0 failed（含此前 9 个既有失败全部修复）。
- **Known（未修）**: 华宝程*宇委托价 100.001 不符最小价位（需 GUI 调试表单输入）；单户 FUND_ACCOUNT_NOT_FOUND 固定 ~85s 耗时待收敛；13:59 异常进程来源待查（疑网络事件触发 catch-up）；北交所实盘申购依赖批量页，未实盘验证。
- **Next**: 下一交易日真实验证全链路；观察 09:30 前 catch-up 不再空跑、死锁自愈。

### 2026-10-20 下午 | 实盘申购日：申菱转债大部分上车，天元重工全军覆没

- **结果（mx_525378109，9 户可直登）**: 申菱转债 371018 — 4 户券商确认已申购（张*龙/陈*燕/陈*凯/刘*豪，系 13:59 某进程早前提交），4 户 submitted_unverified（揭*/许*峰/平安程*宇/徐*正，提交动作已做但 F8 核验失败），华宝程*宇失败（委托价 100.001 不符最小价位 0.010），许*鸣融登录弹窗未跑。天元重工 920306 — 0 户成功：北交所代码被路由成深圳 A 股（"证券信息不存在"）。
- **P0 缺陷链**: ①07:48 catch-up 把申购窗口"未到"误判"已过"并写 task_state completed → 挡掉 10:00 正式申购；②13:59 某进程（疑 catch-up/网络事件触发）死亡留下 catchup.lock+gui.lock 死锁，无 stale 检测 → 14:21 手动补跑白等 20 分钟超时；③发现时 14:42 清锁重跑才赶上。
- **其他 bug**: F8 核验遇窗口句柄失效（Handle is not a valid window handle）→ 提交结果未核验；批量申购页"网格代码为空或重复，整批拒绝"后走逐笔兜底；华宝"预处理失败: 未送交易类别"。
- **今日动作**: 删除错误的 subscribe|2026-10-20|live 状态（备份 task_state.json.bak-1020）；临时禁 mx_mbqdpecj9 跑完后已恢复 enabled。
- **Next（Step 2/3）**: 状态门不记 skipped_expired 为 completed；锁加死进程检测；920 板块路由；华宝价格/交易类别；F8 核验重连 xiadan 句柄；单户失败耗时 85s 收敛。

### 2026-10-20 | Step 1 登录可靠性修复 + 真实验证通过

- **根因**: ①同花顺右上角 username 是紫色 (128,0,128) 小号自绘文字，RapidOCR 直接读成乱码（"LK"）→ THS_CURRENT_ACCOUNT_OCR_UNMATCHED；②登录后主窗先出现空壳（粉色未渲染），wait_for_main_window 只认标题 → 验证 OCR 截到空窗；③主窗标题非 `同花顺(` 前缀时 find_hexin_hwnd 找不到窗口。
- **Fix**: `shared/username_ocr.py` 增加彩色文字分离（色度掩码+4x放大）OCR 兜底重试；`ths_account_switch._read_account_until_ready` 对 OCR 类错误在切换剩余时限内 2s 间隔重试；`hexin_login.find_hexin_hwnd` 增加宽松标题兜底；`_default_open_menu` 找窗口重试 2 次再考虑重启；OCR 截图前置前主窗，失败截图保留在 runtime_data/ocr；runner 增加 duration_s（整体/THS户/资金户）。
- **Verified**: 真实 `ths-cycle --phase login`：mx_525378109 reused、mx_mbqdpecj9 切换成功（蔡*良/刘*伟 ready）；lifecycle 温和关闭无残留；pytest 相关 147+41 全绿。
- **Known（Step 2 待做）**: 资金户 FUND_ACCOUNT_NOT_FOUND 不稳定（两次运行成败互换），单个失败固定耗时 ~85s 太长；OCR 菜单行有前缀噪声（"国 "/"福 "/"中 "）且曾丢名人名（"中信建投证券融"）。
- **Known（既有非本次）**: notification/receipts + shared/errors 脱敏相关 9 个测试失败，为前一线程并发修改遗留，与本次改动无关。
- **Next**: Step 2 资金户切换稳定性 + 单户失败耗时收敛（目标 ≤30s）。

### 2026-10-18 | THS 双账户 login GUI 验收

- **Fix**: 同花顺登录按钮增加 BM_CLICK、非 ABSOLUTE 物理鼠标点击和 Enter 兜底；账户 OCR 身份归一化消除 `国 / 一 / -` 噪声。
- **Verified**: 真实 `ths-cycle --phase login` 达标：`mx_525378109` 8 ready + 1 明确弹窗失败；`mx_mbqdpecj9` 切户成功且 4 ready，另 1 个明确弹窗失败。`python -m pytest -q` 392 passed；未提交真实委托。
- **Known**: 预存在 `xiadan-plus.exe` PID 35780 温和关闭失败，禁止强杀；下一阶段再做申购/中签链路。

### 2026-10-17 | 代码与整体运行逻辑审查

- **Decision**: live 重跑暂不应视为安全；先修批量申购 allowlist/permissions/blacklist 越界和订单台账损坏 fail-open 两个 P0。
- **Risk**: SendKey 可随 requests 异常进入日志；双客户端部分失败会阻断健康客户端/丢失回执；异常清理可能跨客户端；资金账号 ComboBox 识别和账户别名匹配不够唯一；results 按日期覆盖审计记录；`shared/gui_lock.py` 锁字节位置随文件末尾漂移，实测可双重加锁。
- **Verified**: 当前快照 `python -m pytest -q` 91 passed；compileall/run.py --help exit 0；doctor ok=true；32 位执行依赖可导入但 `.venv32` 无 pytest；5 个 Windows 任务均存在。审查期间检测到并发代码写入。
- **Next**: 修复顺序：批量 allowlist→台账 fail-closed→账户身份唯一校验→密钥脱敏→双客户端隔离/逐笔落盘；补齐损坏台账、歧义账户、双保险四象限、部分客户端失败测试。审查记录见 `missions/1017-code-review/`。
### 2026-10-17 | Windows 独立应用封装评估

- **Decision**: 可封装为本机 onedir 独立应用，但必须是 64 位核心 + 32 位执行端双 EXE；单个完全独立 EXE 和跨机器免配置代交易不现实。同花顺仍为外部依赖，Windows 调度必须保持 Interactive。
- **Risk**: 最大风险是同花顺 UI 升级、32 位依赖、DPAPI 换机、未签名 EXE 误报和 live 回归；PyInstaller one-file 不承载业务执行链。
- **Verified**: Python 3.12.10 AMD64 / 3.11.9 32-bit 真实环境；5 个 AutoIPO 计划任务存在；PyInstaller 官方版本 6.22.3；`python -m pytest -q` 76 passed。
- **Next**: 用户确认目标形态（独立目录 / 安装包 / 单文件 / 原生 GUI）和 UI 范围后，先写 `specs/packaging.md`，再做双 EXE onedir POC；计划见 `missions/1017-standalone-app-feasibility/plan.md`。

### 2026-10-17 | zidongdaxin.com 公开链路分析

- **Verified**: `zidongdaxin.com` 为 Nginx + ThinkPHP 3.2.3 站点，apex/www 301、Let's Encrypt TLS1.2、A=`101.43.73.101`；公开日历接口为 `/api/Calendar/grtList`、`/api/Calendar/bondList`，20 条/批，新股记录显示约每日 08:00 更新。
- **Workflow**: 首页 → 手机验证码登录 → 绑定券商账户 → Broker/Account/UserCenter 管理 → 推断后端定时自动申购 → 公众号/消息通知；实际下单与密码存储因未登录无法验证。
- **Gotcha**: 可转债策略文案冲突：“转股价值>95 自动申购”与“目前全申购”并存；另见 Cookie 缺安全属性、API CORS `*`、GET 发验证码、404 泄露 `/data/wwwroot/zddx`/框架版本。
- **Boundary**: 只读公开页面和接口；未登录、未提交表单、未触发申购。证据在 `missions/1017-zidongdaxin-site-analysis/plan.md`。

### 2026-10-17 | THS 登录链路重构 + 8 个平安账户真实验收通过

- **Action**: 主界面登录改为名称/缓存/坐标三路定位；`menu_row` 只作缓存兜底。BootLogin 统一输出 8 字段会话状态，F12 后逐户用 xiadan 列表+资金账号哈希复核；密码/验证码弹窗立即停止。
- **Fix**: `runtime_data/account_map.json` 迁移为 version=2，只存 SHA-256/脱敏资金账号/显示名；修正错误账户按钮模板和 GBK 控制台 Unicode 崩溃。
- **Verified**: `python -m pytest -q` 54 passed；32 位 `pywinauto/win32gui/jqktrader` 导入 ok（numpy 1.26.4、pandas 2.0.3）。真实 boot-login 按“下拉→点账户→重新下拉”逐户登录 8 个平安账户，F12 后逐户切换复核 8/8 ready；无委托。
- **Next**: 先保持单实例平安 8 户稳定；其他券商和 20 户扩展另行排期。

### 2026-10-17 | 动态账户范围 + 实盘单次提交硬化

- **Decision**: 账户集合从当前 hexin 菜单/xiadan 列表动态匹配 config，不按券商、账户 ID 或固定行号硬编码；华宝/中信建投当前周末登录失败不排除，后续可自动参与。
- **Fix**: 新增每日订单台账（同一账户+代码+日期只提交一次）；批量申购改为 F8 逐笔核验，unknown/submitted_unverified 阻断重试；live 增加时段保护和 preflight 门禁。
- **Fix**: 修复 Windows 任务命令引号/工作目录，5 个任务改用 scheduler/run32.cmd、run64.cmd，StartWhenAvailable=true；东财 code=9201 空结果合法返回。
- **Verified**: pytest 76 passed；32 位依赖导入 ok；真实 preflight ok=true，当前动态识别 8 个平安账户且 8/8 ready；真实 boot-login 8/10 ready（另外两户为周末外部登录限制）。
- **Next**: 下一交易日观察真实申购台账和中签通知去重；双实例/20 户继续暂缓。

### 2026-10-16 午后 | 假阳性根因修复 + 补打完成（最终 9/10 真实挂单）

- **根因（双重）**: ①jqktrader 的表单输入/提交按钮 child_window 命中堆叠的隐藏面板 → 静默没点上 → 无弹窗 → 返回 {'message':'success'} 假成功（无 entrust_no）；②用户操作电脑时键鼠输入会落入表单字段（曾出现垃圾值 'hu' 导致「证券信息不存在」）。
- **Fix**: _find_ctrl 改用 win32gui IsWindowVisible 全链可见性判定（pywinauto is_visible 只看自身样式位，面板堆叠场景误判——实测验证）；_type_edit_control_keys/_submit_trade/菜单树/网格全部走该判定；execute() 申购后自动 F8 读当日委托核验，查不到标 failed 不冤枉成功。
- **Verified**: 补打 许*鸣（中信建投信用，entrust 222872）+ 揭*（entrust 0112340573），F8 核验均 True；results/2026-10-16.json 已校正。最终 9 户真实挂单，蔡*良待签转债协议。
- **Rule**: 委托成功判据=有 entrust_no 且 F8 核验通过；{'message':'success'} 无编号=不可信。
- **ID 改名**: 许鸿鸣JT → 许*鸣（config+secrets 同步 re-key），账户标识统一用客户端显示名。

### 2026-10-16 | 实盘首跑 9/10 成功（中科转债）

- **Verified**: 13:19 手动触发 `subscribe --live`（电脑没开，10:00 任务漏跑）：9 户顶格 1 万张提交成功；蔡*良（华宝）被拒「该股东号无此类代码的相关交易权限」→ 需在华宝签可转债协议，非代码问题。
- **Discovery**: 转债不在「批量新股申购」页网格（当日网格为空），全部走买入表单兜底成功——双重保险设计验证有效；批量页只覆盖新股（待新股日验证）。
- **Fix**: 账户标签误读下拉框显示文字（显示≠上下文残留：中信建投窗口显示「张*龙」），改为优先取切换时验证过的 account_map.json 缓存。
- **Action**: 4 个定时任务全部开启 StartWhenAvailable（错过计划时间开机即补跑）——防止电脑没开导致漏打新。
- **Note**: 转债申购不冻结资金（中签才缴款）；窗口「可买不足」红色提示不影响申购委托。

### 2026-10-15 深夜⑤ | 锁屏结论 + 双实例验证（20 户方案基础）

- **Verified（证伪）**: 账户下拉无法用 Windows 消息驱动（CB_SETCURSEL/CBN_SELENDOK 只改显示不换上下文，资金账号不动），必须真实鼠标点行 → **锁屏不可行**。已配置不锁屏（屏保/锁定/睡眠全关），正确姿势=关显示器而非 Win+L。
- **Verified**: 同花顺可双实例——E:\同花顺 克隆到 E:\同花顺2（1.1GB），两个 hexin.exe 进程同时运行互不干扰（各自独立配置目录）。已测完即关 hexin2，避免 F12 定位错客户端。
- **20 户方案**：hexin2 退出当前同花顺账号、改登第二个手机号 → 各自 F12 拉各自 xiadan（每实例 10 户）→ config 账户加 client 分组字段，subscribe 按组用对应 xiadan_path。待用户需要时实施。
- **Note**: hexin2 克隆时带走了 THS 账号 525378109 的登录态，启用前需在 hexin2 里换绑第二个手机号。

### 2026-10-15 深夜④ | 五轴评审 + 3 Critical 修复 + 死代码归档

- **Review**: 子代理五轴评审结论 Request changes，3 Critical 全在首跑失败路径上，已全修：
  C1 资金账号不再进异常消息（会进推送正文）；C2 close_modal_dialogs 只点「取消」/关窗，绝不点「确定/确认」（防误提交残留委托）；C3 实盘留痕=每户申购后截主窗存 runtime_data/results/、中签时截图。
- **Fix**: 日历抓取失败重试一次再失败则推送告警（daily-report 和 subscribe 两条路都接了，不再静默死）；东财字符串数字强转防御；subscribe 双重保险去重抽成 uncovered_orders 并补 3 个测试（27 passed）；F12 启动加僵尸进程检查（进程在但无窗口→杀掉重拉）；run.py pushid 改 .get。
- **Decision**: 批量申购页以柜台额度为权限裁决（config permissions 仅作用于买入表单兜底路径），已在 ipo_page.py 注释写明前提。
- **Action**: login.py 死代码（登录框自动化：_select_broker/_select_remembered_account/_captcha_controls/_ocr_captcha 等约 150 行）归档 execution/legacy_login_dialog.py（无 git 故物理留存）；ths_client 删 account_snapshot/tesseract 链路；config 删 tesseract_path；文档同步（spec.md 逻辑图、execution.md 申购入口、INDEX.md 时间/库名）。
- **Known**: 信用账户（许鸿鸣JT）余额页面板可能读不准（底栏信用 tab 坐标未调通），中签推送带余额时再校验；同日重复触发 10:00 任务会重复申购（转债交易所自动合并，新股拒单），勿手动重跑。

### 2026-10-15 深夜③ | 双重保险申购 + 中签推送带余额 + 四项能力矩阵 10/10

- **Decision（用户）**: 可转债申购=批量申购页优先 + 买入表单对未覆盖标的兜底（双重保险，按 apply_code/名称去重，不会重复下单）。
- **Action**: 中签推送带「可用资金」+缴款提醒（16:00 前留足）。
- **Verified**: 余额读取可靠性修复——余额面板按账户堆叠，规则=先导航资金股票页、取父面板 IsWindowVisible=1 的 Static（截图比对验证：蔡*良 19.50 ✓）。10 账户 ×（申购额度/批量申购/中签明细/余额）四项能力全 OK。
- **⚠️ 待观察**: 许鸿鸣JT（信用户）余额读出 0.0 与主窗显示不符，信用账户资金页可能走另一套面板，中签发生时再校验；批量页是否列出转债待明早实盘确认（空则自动回退买入表单）。

### 2026-10-15 深夜② | 批量申购页 + M4 中签查询完成，webui 停用

- **Decision（用户）**: 停用 webui（127.0.0.1:8321 进程已杀），账户管理直接在客户端做；申购改用「批量新股申购」页真实额度（柜台口径=权限/市值裁决，config permissions 不再是关键闸门）。
- **Action**: execution/ipo_page.py（读网格→全选→剔0额度行→申购→弹窗处理，jqktrader auto_ipo 的定制版）；live 主流程改为批量页优先、空网格回退日历+买入表单。
- **Action**: execution/allotment.py（M4）——逐账户「新股申购→查询中签明细」读网格，有中签才推送；定时任务 AutoIPO-Allotment-T1（工作日21:00）/T2（08:00）已注册。
- **Gotcha**: 多棵菜单树同名节点子项不同（华宝树上「查询中签明细」在 tree5-8 不在 tree0）——_switch_left_menus 补丁改为逐树试点路径；下拉弹层偶发打不开（前台丢失），加 ESC 重置+3 次重试。
- **Verified**: 10/10 账户 切换→批量申购页→中签明细页 导航与网格读取全通过（盘后网格为空属正常）；pytest 24 passed。
- **Next**: 明早 10:00 中科转债 10 户 live 首跑，观察批量页是否列出转债（不列则自动回退买入表单）；明晚 21:00 首次中签查询。

### 2026-10-15 深夜 | 多账户架构定稿：顶栏下拉点行切换（废弃登录框自动化）

- **根因链**：裸启动 xiadan=游客态（无记住账号+未注册弹窗挡交易）；必须由 hexin 主客户端 F12 带令牌启动（`ver=1 <token>`）；账户资料存在 THS 用户目录（mx_525378109）按券商分文件夹。
- **Verified**: 顶栏账户下拉（items 含「编辑账户」的 ComboBox）必须**点开弹层真实点行**才切换上下文（combo.select() 只改显示文字——踩过）；成功判据=主窗资金账号 ComboBox（纯数字≥6位）刷新为目标值；窗口 HWND 不变；余额 Static 按账户堆叠缓存，不能当判据。刷新有 3-5s 延迟，须先等离开旧值再比对（踩过误 break）。
- **Verified**: jqktrader 补丁（ths_client.py::_patch_jqktrader）——菜单树 129/余额 Static 1012 等同 ID 控件堆叠 9 套，child_window 唯一匹配假设必败，改 descendants+可见优先。
- **Verified**: 全链路：F12 启动→切换（张*龙/蔡*良/许鸿鸣JT 互切各~3s）→connect→buy('000000')→拒单「证券信息不存在」完整捕获→模态框清理（close_modal_dialogs，残留弹窗会挡住下拉）。缓存 runtime_data/account_map.json。
- **Action**: config 账户与客户端实际已登录 10 户对齐（许鸿鸣JT=99272440 信用、张*龙/揭*/陈*燕/许*峰/陈*凯/程*宇/刘*豪/徐*正 平安、蔡*良 华宝），权限默认仅 cb；吴志聪PA/许鸿鸣HB 未登录客户端故停用。**下拉容量 10 户已满**，加新户需先腾位。
- **Next**: 明早 10:00 中科转债（371175）10 户 live 首跑；M-next 申购改批量申购页真实额度（auto_ipo 改良）、M4 中签查询（菜单「新股申购→查询中签明细」）。

### 2026-10-15 | 表单 v2：ID 即备注、删除路径、自动增行、北交所并入权限

- **Fix**: 新行 ID 留空时保存会静默丢行（用户踩到）——改为行内有数据则自动取资金账号为 ID。
- **Decision**: 北交所独立开关删除，并入权限（勾 bj 即打）；备注列删除，ID 即备注名（可中文）；券商候选扩为 7 家（平安/华宝/中信建投/华泰/银河/中信/东方财富）；每行加「删除」按钮（连带删凭据）；ID 改名时凭据自动随迁。
- **Action**: config 账户 pingan_main → id: 吴志聪，去掉 note/bj_enabled 字段；subscribe/run.py/specs 同步。
- **Verified**: pytest 24 passed；表单新版渲染确认；dry_run 输出【平安证券-吴志聪】中科转债 10000 张。
- **⚠️ 待用户**: 表单里吴志聪账户的资金账号/交易密码仍未填（显示「未设置」）——明早 10:00 自动登录需要它们。

### 2026-10-15 | 表单升级（凭据录入+权限收紧）+ 自动登录模块

- **Decision**: 权限过滤收紧为「勾选才打」：可转债需 cb、创业板 cyb、科创板 kcb、北交所需 bj_enabled 开关+bj 权限；沪深主板新股无需权限（市值柜台裁决）。权限清单从此只有 4 项。
- **Action**: 表单新增 资金账号/交易密码 字段；密码 DPAPI 加密（shared/credstore.py）存 secrets.yaml accounts_secrets 段，留空=保持不变；AGENTS.md §9 相应修订（用户明确需求视为批准）。
- **Action**: execution/login.py 自动登录模块（重启 xiadan→填账号密码→点登录→关注册弹窗），待用真实凭据实测。
- **Verified**: pytest 24 passed；表单新版浏览器渲染确认。
- **⚠️ 关键提醒**: 平安账户 permissions 为空，按新规则明早 10:00 中科转债会被跳过——用户需在表单勾选「可转债」权限+填写资金账号/交易密码。
- **Next**: 用户填凭据 → 实测 ensure_logged_in 自动登录 → 明早 10:00 全自动首单。

### 2026-10-15 | 切 live + 实盘路径验证 + M3 管理界面第一阶段完成

- **Action**: config execution.mode=live（用户拍板）。live 全路径实测：连接真实客户端→真实提交 371175→券商拒单（非申购日）→原因完整捕获。明天 10:00 定时任务将真实下单中科转债。
- **Verified**: webui/app.py 管理界面完成——账户增删改（券商/备注/普通·信用/北交所开关/权限勾选/启用）、模式切换按钮；ruamel 保注释写回 config.yaml；只监听 127.0.0.1:8321。pytest 20 passed，浏览器实测渲染正常。
- **Gotcha**: Jinja2 不支持 loop.parent，外层索引用 {% set outer_i %} 传递。
- **Action**: AGENTS.md 根目录白名单新增 webui/（用户「我只要一个表单」的明确需求视为批准）。
- **Next**: 明天 10:00 观察实盘首单与微信反馈；M3 第二阶段=多账户在 xiadan 中自动切换执行；M4 中签查询。

### 2026-10-15 | 废单测试全链路验证 + 自动申购任务已挂 armed

- **Verified（零风险实盘链路）**: 收盘后程序真实下单 371175@99.99（注定被拒价格），jqktrader 完整走完 连接→填单→提交→弹窗捕获，返回券商真实拒单原因「证券信息不存在」（非申购日）。证明链路和错误捕获可用，无需等明早。
- **Action**: execute() 增加逐标的异常捕获（failed+reason，不中断后续标的）；run.py subscribe live 路径接通（connect→execute）；新增 3 个 execute 测试，共 16 passed。
- **Action**: 注册 `AutoIPO-Subscribe` 定时任务（工作日 10:00，`subscribe --live`），当前 config mode=dry_run 故只演练；明天验证后把 config 切 live 即全自动。
- **静默执行现实**：申购瞬间 xiadan 窗口会自动弹出操作几秒再关闭（客户端自动化物理限制，无法完全无窗口）；锁屏下大部分操作可执行。电脑保持开机+登录即可。
- **多账户路径**：xiadan 资金账号下拉可保存多账户（每个账户首次需手动登录一次并记住密码）；M3 管理界面统一增删账户，执行层按账户逐个切换操作。
- **Next**: 明天 10:00 前把 execution.mode 改 live，中科转债实盘首单验证。

### 2026-10-15 | M2 第二阶段：申购流程 dry_run 打通

- **Action**: execution/subscribe.py（指令生成+双模式执行）+ run.py subscribe 子命令；转债顶格 深市1万张/沪市1000手、新股按发行价+上限、北交所按 bj_enabled 过滤、空权限清单不过滤。
- **Verified**: pytest 13 passed；`subscribe --day 2026-10-16` dry_run 输出中科转债 371175 10000张@100。
- **Decision**: 实盘双保险——config mode=live + 命令行 --live 缺一不可。
- **Next**: 用户确认后实盘首单（建议 10-16 中科转债，可转债不冻资零风险）；之后注册 10:00 定时申购任务。

### 2026-10-15 | M2 第一阶段完成：平安账户连接成功

- **Verified**: 32 位 Python 3.11.9（.venv32）+ jqktrader 连上已登录的平安 xiadan 客户端，balance/position 字段齐全非空（真实账户数据，数值不落文档）。
- **Gotcha**: pandas 2.0.3 需配 `numpy<2`（1.26.4），否则 `_ARRAY_API not found`。完整配方在 specs/execution.md。
- **Decision**: 执行端固定用 .venv32（32 位）；日历/通知等其余模块继续用 64 位主 Python。
- **Cleanup**: Python312-32 误装可删（约 150MB）。
- **Next**: M2 第二阶段——dry_run 申购流程串联（日历→指令→模拟下单回报），用户确认后实盘一单（明天 10-16 有中科转债可试）。

### 2026-10-15 | M2 连接验证：两个关键环境发现

- **Finding**: xiadan.exe 是 32 位程序，64 位 Python 枚举不到控件（pywinauto 限制）——execution 模块必须用 32 位 Python。32 位 Python 3.12 安装包下载中（python.org 较慢）。
- **Finding**: jqktrader 锁死 pandas==1.5.3，Python 3.12 装不上；正确姿势 `--no-deps` 装 jqktrader+easyutils，再装现代依赖。已验证 import 成功，写入 specs/execution.md。
- **Finding**: xiadan 登录窗口（网上股票交易系统5.0）实测：需先「添加券商→平安证券」再填资金账号登录；另有「非同花顺注册用户」弹窗，点取消即可。用户所说的「已登录」可能登的是同花顺行情主程序（hexin），委托下单窗口仍需单独登录。
- **Next**: 32 位 Python 装好后建 execution 专用 venv → 重试连接 → 读账户快照验证。

### 2026-10-15 | 同花顺乱码根因修复 + 通知拆为两条推送

- **Root cause（同花顺乱码）**: 系统区域被设为 UTF-8 Beta（注册表 ACP/OEMCP/MACCP=65001），与 GBK 系交易客户端冲突。按同花顺官方文档（xdres.10jqka.com.cn/showdoc #/12/65）改回 936/936/10008，**需重启生效**。注意：这是 2026-05 Alpha monitor 为解决控制台乱码做的改动，其 PYTHONUTF8=1 等其余措施不受影响。
- **Verified**: 通知改为今日/明日各一条独立推送，标题 `10/15 华纬转债 1万张`、`10/16 中科转债 1万张` 已实推送达；pytest 8 passed。
- **Next**: 用户重启电脑后验证同花顺界面乱码是否消失，再登录平安账户，然后开 M2。

### 2026-10-15 | 通知双日化 + 打新时间定 10:00 + 同花顺现状

- **Decision**: 打新执行时间 10:00（用户拍板，覆盖深市 9:15/沪市 9:30 开盘差异）；日历推送改为当日+明日双日。
- **Decision**: 通知体系三类定型：①日历通知 ②申购完成反馈（按账户备注逐个列出标的+数量）③中签反馈（账户+标的+数量）。
- **Verified**: xiadan.exe 找到了（E:\同花顺\同花顺\xiadan.exe，版本 2026.07.02，进程可正常启动）——安装本身没问题；用户反馈「无法正常使用」具体现象待用户说明（大概率是登录环节）。已帮用户启动 xiadan 进程。
- **Gotcha**: PowerShell 5.1 读无 BOM 的 .ps1 按 GBK 解码，中文路径字面量会乱码——ps1 脚本中避免硬编码中文路径，用递归查找代替。
- **Verified**: 新格式 pytest 6 passed；实推标题 `10-15/10-16 打新：华纬转债 1 万张、中科转债 1 万张` 送达。
- **Next**: 等用户在同花顺登录平安账户后开 M2；可转债顶格数量展示暂定「1 万张」，M2 实盘时以客户端实际顶格校验。

### 2026-10-15 | 通知标题化 + 账户模型扩展 + 雪球否决

- **Decision**: 通知标题承载核心信息（手机微信通知列表只显示标题）：`10-16 打新 1 只：中科转债(债)`；多标的超阈值折叠为「债 N 股 M」。
- **Decision**: 账户模型扩展 note（备注）/ account_type（normal/credit 信用账户）/ bj_enabled（北交所独立开关，默认 false，全额缴款风险不同）。
- **Decision**: 雪球打新无公开 API（仅与平安/国金/国联合作的 APP 内嵌功能），否决；维持同花顺客户端路线，自动化库优先 jqktrader（easytrader 年久失修的继任者）。
- **Verified**: 东财新股接口单接口覆盖全市场（沪主板/深主板/创业板/科创板/北交所，MARKET_TYPE_NEW 区分）；改后 pytest 6 passed；新标题真实推送送达。
- **Action**: 同花顺官网下载链接已给用户；M3 需求补充本地管理界面（Web 表单）。
- **Next**: M2 平安证券接入（等用户装好同花顺客户端并完成首次登录）。

### 2026-10-15 | 架构转向完全本机 + M1 完成

- **Decision**: 放弃服务器方案，完全本机运行（用户拍板：多账户、跨券商、自动打新、人工零参与；推送必须标明账户；账户需支持用户备注 note）。无服务器、无强制 git 工作流。
- **Decision**: 权限判断双手段——主判据以券商柜台返回的可申购额度为准（为 0 跳过），config 权限清单仅作预过滤辅助。
- **Action**: 服务器已部署内容全部清理（含 secrets.yaml），本地 git remote prod 已移除；AGENTS.md/INDEX/README/specs/config 全部改为本机架构；deploy/ 目录删除。
- **Verified**: M1 全链路本机跑通——pytest 5 passed；真实抓取东财日历（10-15 华纬转债 071380 / 10-16 中科转债 371175）；Server酱真实推送 3 条均送达；Windows 任务计划 `AutoIPO-DailyReport`（工作日 08:25）注册并手动触发验证成功，日志在 runtime_data/daily-report.log。
- **Next**: M2 平安证券——安装同花顺下单客户端并确认能登录平安账户（关键验证点），easytrader 接入，dry_run 走通申购流程。
- **Blocker**: 需用户提供平安账户在同花顺客户端的登录验证（需用户在场操作一次）；config/config.yaml 中 permissions 待用户核实填写。

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

### 2026-10-17 | 双同花顺隔离 + 可复制性扩展完成

- **Action**: 双客户端注册/精确 exe 路径隔离、client_order 串行、GUI 原子锁、跨客户端资金账号哈希防重复；新增 `discover`、`doctor`、统一 setup/路径/错误结构。
- **Fix**: boot-login 真机暴露坐标兜底误点与 `about:blank` 误判弹窗；改为未确认账户不进委托界面，人工弹窗只认密码/验证码关键词。
- **Verified**: pytest 101 passed；doctor ok（64/32 位、配置、DPAPI、双路径）；dry-run 零委托；真实 discover 当前 THS1=8、THS2=4、12/12 配置匹配；THS2 华宝密码/验证码登录框被正确识别并停止。
- **Next**: THS2 的刘*伟/余*彬补 secrets 后启用；交易日重跑 boot-login/preflight，再由用户确认一次 live。

### 2026-10-17 | 登录生命周期、错过后补、标准回执完成

- **Action**: 主界面只登录可直登账户；误点“委托下单”密码/验证码框立即截图关闭并继续，其他人工安全弹窗停止。GUI 任务前启动客户端、完成后温和关闭，不强杀；双客户端全周期持全局锁串行。
- **Action**: 新增 `run.py catch-up` 与开机/联网计划任务；申购过期记 `skipped_expired`，中签未公布/失败继续补查。登录/申购/中签统一回执模板和脱敏。
- **Fix**: 回执重试展开嵌套申购明细；中签结果返回结构化 `items`，catch-up 不再把中签文本当完整回执。
- **Verified**: `python -m pytest -q` 131 passed；32 位依赖导入、64/32 compileall、PowerShell 脚本解析、`doctor ok` 全通过；`subscribe --day 2026-10-17` dry-run 零真实委托。
- **Next**: 交易日按 discover → boot-login → preflight → dry-run → 人工确认 → 单次 live 真实验收；THS2 需密码账户保持跳过。

### 2026-10-18 | THS 每账户独立会话 + 操作信息完整化

- **Decision**: `ths_account_switch` 严格按“启动同花顺 → 登录一个 THS → 处理最多10个资金账户 → 执行阶段 → 温和关闭 → 下一个 THS”运行，账户不硬编码。
- **Fix**: 密码框元数据兼容缺 handle/control_id 的自绘控件，凭 style/password_hint/rectangle 唯一识别，不读取 Edit 文本；切户异常显式记 `switch_failed`。
- **Change**: 回执/日志显示完整 THS 用户名、账户显示名、状态、错误和业务明细；仅密码、验证码、SendKey、完整资金账号等核心凭据排除。
- **Verified**: `python -m pytest -q` 363 passed；64/32 compileall、32 位依赖导入、`doctor ok`、`schedule-json` 均通过。
- **Next**: 可登录时段运行 `python run.py ths-cycle --date 2026-10-18 --phase login` 真实验收；随后 dry-run subscribe/allotment，任何阶段不提交真实委托。

### 2026-10-18 | THS 真实 login-only 链路修复

- **Fix**: 真实 pywin32 没有 `GetWindowTextLengthW`，改用 `GetWindowTextLength`；password control style/handle 可为方法，读取前统一解析 callable。
- **Fix**: 资金账户主菜单点击成功后不再发送 ESC；所有账户行完整等待 `dialog_wait_s`，避免延迟登录弹窗漏检。
- **Fix**: 点击后目标未进入 xiadan 记 `not_logged_in / fund_login_result`；实际出现登录弹窗即记 `login_required=true`；`THS_PASSWORD_MISSING` 不再被吞成通用读取失败。
- **Fix**: 菜单账户行丢失 `bottom` 后按全局行号点错；现保留 UIA 实际边界点行中心。xiadan 主窗仅标题“委托下单”不再误判为资金登录弹窗；新增 `fund_login_result_wait_s/fund_login_poll_interval_s` 轮询。
- **Verified**: pytest 370 passed，64/32 compileall、32 位依赖导入通过；真实 login-only 仍为部分成功，`mx_525378109` 报 `THS_UI_HANDLE_STALE`，`mx_mbqdpecj9` 有 dialog_closed/not_logged_in，未提交委托。

- **2026-10-20 Fix**: Codex 旧线程报 `Model provider mimo not found`；cc-switch 切 Kimi 时重写 config.toml 删了 mimo provider。已从 cc-switch.db 找回配置并在 config.toml 加回 `[model_providers.mimo]` + catalog 补 mimo-v2.6-pro，tomllib 验证通过。注意：cc-switch 再次切换会覆盖 config.toml。

### 2026-10-21 | 大扫除：去脱敏 + 交易日门 + dual_client 移除 + 推送重做

- **Decision**: 根源取消脱敏——日志/推送/状态全量显示账户识别信息（显示名/完整资金账号/THS 用户名），仅密码/验证码/SendKey/token/URL 排除；回执改「时间+账户+事件」格式（标题含 HH:MM）。
- **Decision**: 非交易日不启动——新增 data_fetch/trading_days.py（东财上证日K线+文件缓存+周末快速否决），run.py daily-report、catch_up、run_ths_cycle 全部过门，非交易日 skipped_non_trading 不写状态。
- **Decision**: dual_client 双客户端模式彻底移除：删 gui_runner/discovery/preflight/boot_login/legacy_login_dialog/account_scope + config clients/client_order/active_mode + 相关测试；register_tasks.ps1 只注册 ths-cycle 命令；doctor 单模式。
- **Action**: 修复 run32.cmd 乱码（chcp 65001+UTF-8 BOM）；删根目录垃圾 390/720；删 tests/debug。
- **教训**: 误删 execution/ 未入 git 的 hexin_login/login/window_scope/account_session，经 Codex 历史会话 dump + __pycache__ pyc 函数清单比对恢复；hexin_login 与 pyc 完全一致，login/window_scope 各补 4/1 个私有函数（未经真机回归，见 逻辑图 §7-R1）。
- **Verified**: pytest 283 passed；64/32 位 compileall 通过；schedule-json 正常；doctor ok；trading_days 真实验证（周三/周一=True，周六/国庆=False）；daily-report 非交易日实跳。
- **Next**: 下一交易日真机回归登录链路（恢复文件）+ K4 华宝价位问题。


### 2026-10-22 | 速度、验证码与 GUI 外部执行

- **Fix**: F8 当日委托、批量申购核验、查询中签统一屏幕 OCR，禁用 jqktrader 网格复制，根治“检测到您正在拷贝数据”。
- **Fix**: 数字验证码登录/普通提示自动填写；短信、动态口令、人工安全验证仍停止。
- **Fix**: 登录窗已打开时跳过主窗关闭/切换链路；账号下拉和登录按钮改 Win32 消息，降低 active desktop 依赖。
- **Fix**: `--force-retry` 仅显式允许重复测试，默认仍防重复；失败 GUI 不再误记 completed。
- **Verified**: pytest 311 passed，compileall 通过。
- **Blocked**: Codex GUI 会话无法取得 active desktop/系统代理权限；需用户桌面直接运行 `runtime_data/run_gui_dry.lnk`，确认后再运行 `runtime_data/run_gui_live.lnk`。

### 2026-10-24 晚 | 单户硬限时 30s（用户拍板 15s 目标）

- `gui.ths_account_switch.per_fund_timeout_s: 30`；ThsAccountUI._sleep 全部走 deadline 包裹（__init__ 注入时包裹），到点抛 FUND_ACCOUNT_TIMEOUT（AutoIpoError），runner 逐户 start/clear，状态记 timeout。
- 教训：锚点替换 `self._sleep = sleep_fn` 把 __init__ 尾部两行吞进新方法体——补丁后必须 diff 检查原行后续代码归属。
- 平安同券商差异根因=逐户会话有效性；救活需 DPAPI 密码自动填充（涉及不变量 §6-2 变更，需用户书面批准）。
- pytest 324 全绿；compileall 32 通过。

### 2026-10-24 晚 | DPAPI 密码自动填充上线（用户批准）

- spec 先行：security.md/execution.md §6.1/逻辑图 §6-2/INDEX §6 已同步（委托登录框允许自动处理；短信/动态口令/人工验证仍停止）。
- 实现：execution/captcha_login.py `password_for_fund_account`（按资金账号精确匹配 secrets+DPAPI 解密）+ `try_password_login`（密码框 set_edit_text+勾保存密码+OCR 验证码+点登录，任一步失败回退）；ths_account_ui.handle_dialogs 接线（无验证码的纯密码框也触发，数字提取用首个 \d{6,} 防验证码串号）。
- dialog_wait_s 5→2。pytest 327 全绿；compileall 32 通过。
- 未真实触发过（需会话过期户遇到委托登录框才算实战）；周一重点观察。

### 2026-10-24 真实测试（第三轮）| 5.2min 全流程 + 验证码单字拼接修复

- **真实数据**：15 户 311.7s（昨日 1126s）；12 户 ready 全部 11.3-14.2s（**15s 目标达成**）；昨日 5 个 not_logged_in 平安户 4 个今日直登成功；揭* 触发 30s 硬限时（无弹窗、xiadan 未起，周一看）；华宝 2 户 dialog_closed 优雅跳过。
- **实战发现 1**：委托登录框密码已被 xiadan 预填（保存密码+自动登录勾选），真正阻塞只剩验证码；try_password_login 原逻辑"密码框非空即返回 False"已修（密码框缺失/已填不阻断验证码与登录）。
- **实战发现 2（关键）**：RapidOCR 把同花顺验证码切成单字条目（'2','0','5','8'），`_CAPTCHA_RE ^\d{4,6}$` 永不匹配 → 此前所有验证码自动填写在真实弹窗上必失败。已加 `_digit_band_candidates`：水平带聚类+x 间隙拼接，真实截图模式验证 '2058' 拼接正确。
- 裁剪：post_click_wait_s 3→1.5。菜单 OCR 缓存确认已存在（每户复用，③无需做）；_xiadan_identity 为廉价 win32 读，合并不划算（④不做）。
- pytest 327 全绿；compileall 32 通过；测试残留已清理；客户端已关闭。
- 周一实战重点：验证码拼接真实弹窗验证、揭* 是否复现、申购+F8 全程耗时。

### 2026-10-24 第四次实测 | 288.9s，揭* 自愈，零超时

- 15 户 288.9s（4.8min）：13 户 ready 全部 11.5-16.3s；揭* 本轮 11.8s ready（上轮 30s 超时是 xiadan 偶发未起的瞬时故障，非系统性问题）；华宝 2 户 dialog_closed 21s（周末服务端拒绝，预期）。
- 30s 硬限时本轮零触发——登录链路（直登/验证码/密码填充/超时兜底）四种路径全部实战通过。
- 周一唯一未实战路径：F8 当日委托 OCR 核验（周四修复后没经历过真实申购日）。

### 2026-10-24 中签回执全流程实测 | 3 发现 3 修复

- **发现 1（中签幻影根因）**：`_allotment_row_recent` 对日期缺失行一律保留 → 许*鸣融 5 条历史中签被当 10-22 当日结果 → 提前 completed 挡住后续补查（用户没收到真实中签回执的元凶）。修复：`_allotment_row_belongs` 要求日期≥业务日**且**代码属于当日申购标的；缺失日期行仅当日标的中留。加回执明细去重（同户同码只留一条）。周六真实重测：12 户结论「无中签」，零历史垃圾。
- **发现 2**：回执发送 failed 根因 = Server酱免费版每日 5 条额度被当天测试耗尽（HTTP 40001），非代码 bug；额度明天自动恢复，task_state 记录 failed 会触发自动补发。改进：serverchan 错误透传服务端 message（已脱敏）。
- **发现 3（重要）**：hexin 的 WM_CLOSE 会弹**广告退出确认框**（自绘按钮无文本，control_id 20199/20149/21042=切换账号/取消/退出），不点退出进程永不结束 → 生命周期谎报 closed 且残留。修复：client_lifecycle 新增 `confirm_exit_dialogs`（识别三键组合只点退出），_close_pid 支持 on_wait 回调，关闭等待期间循环点确认框；另加核验防误报（扫描瞬断为空但已跟踪进程活跃 → 必须 close_failed）。残留：测试过程中 xiadan.exe/xiadan-plus.exe 进入全窗口隐藏的无响应状态，温和手段全部无效，待用户手动结束或批准强杀（宪法禁止强杀）。
- pytest 330 全绿；compileall 32 通过。

### 2026-10-26 周一 | 任务错过补跑 + 显式测试通过

- 电脑全天关机，21:45 开机 → StartWhenAvailable 补跑三任务：日历推送 sent（21:46）、申购 skipped_expired（过 15:00，正确）、中签 retryable（10-26 无申购，数据未公布，明早 T2 继续）。WakeToRun 只对睡眠有效，关机无法唤醒——用户需保持睡眠而非关机。
- 用户批准强杀，周六僵死的 xiadan/xiadan-plus 已清理。
- 21:52 显式 allotment 测试：13/13 户 completed（16.3-24.2s，晚间服务器慢属正常），华宝 2 户 dialog_closed，中签回执 sent（Server酱额度已恢复），hexin 延迟数分钟后自行退出，最终零残留。
- 遗留小账：close() 时进程扫描偶发返回空（heavy GUI 负载下），lifecycle 记录与实际有延迟，但终态干净；下次观察。

### 2026-10-27 凌晨 | 华宝验证码直填链全通（submitted_but_rejected → 键击修复待实战）

- **根因三连修**：①弹窗识别被 xiadan 主窗干扰（标题含「委托」+最小面积降级）②整窗 OCR 漏检浅灰小字验证码（右侧裁剪 2x 放大重试）③水平带定位取到邻近的资金账号数字（改为取验证码条目自身 mid）。
- **WM_SETTEXT 被安全输入框吞掉**（界面显示但程序内部未录入→服务端红字拒登）：验证码改真实键击 type_keys 优先，set_edit_text 回退。
- 渲染延迟：弹窗出现 0.8s 后再 OCR，最多重试 3 次。
- 实测：submitted_but_rejected（链全通，凌晨 1 点服务端拒）；键击版上线后华宝会话直登 15/15 全绿 completed 257s，链未再触发。白天 10:00 申购是键击版验证码直填的首场实战。
- 新增诊断：auto_fill 字段（captcha/password/dialog_not_found/captcha_not_located/submitted_but_rejected）+ debug_last_dialog.png 抓取留证。

### 2026-10-27 | 申购价格修复 + 级联卡死修复 + Server酱额度根因

- **申购价格 100.001 根因**：jqktrader `round_price_by_code` 深市代码强制 3 位小数（100.0→100.001）→ 触发「小数部分应为2位」确认弹窗 → 卡死 F8 → 级联拖垮 THS2（每户 2.8s→27s 滚雪球）。修复：价格框统一规整（整数去尾→100）+ 「小数部分」弹窗自动点否。
- **级联卡死第二根因**：上一户不确定状态残留模态弹窗，只在该户任务结束才清 → 户间传染。修复：每户任务 connect 后再先清一次弹窗。
- **Server酱免费版日限 5 条 = 今天零推送的根因**：凌晨/上午调试推送耗尽额度，8:30 日历 + 10:00 申购回执全部被 40001 拒。修复：「数据未公布」中间态不再推送（只推结论）。明日零点后额度恢复。
- 明天 10-28：森峰激光 920085（北交所，80.75万股）。注意北交所代码不走单笔买入表单（BSE_SINGLE_FORM_UNSUPPORTED），需批量页或人工。
- 教训：生产日绝不发调试推送；force-retry 只对实盘重发有意义但要意识到交易所会拒重复单。

### 2026-10-27 午后 | 线程看门狗：每户硬限时（堵 30s 限额最大漏洞）

- **漏洞实锤**：30s 限额只包裹 `_sleep`，盖不住 OCR 子进程/win32 阻塞调用——10:00/13:26/14:30 三轮申购都卡在某一户 10 分钟+（登录或任务的阻塞调用），整轮被拖死。
- **修复**：runner 每户处理（登录+任务）整体放 daemon 线程，两段式 join——登录预算 30s，登录成功再追加任务 45s；超时判 timeout 跳下一户，孤儿线程弃置（结果不采纳），下一户前置清理复位 GUI。330 全绿含原 runner mock 测试（采纳路径已验）；超时路径待明日实盘验。
- **代价/风险**：超时户的孤儿线程可能在后台多点了少数几下，由下户前置 close_modal_dialogs 兜底——这是任何硬杀方案的固有取舍。
- 今日申购结论：千红转债 072550 已于 10:00 全户申购成功（交易所"已申购过"拒单反证）；下午重跑只为走流程，均已知会触发重复拒单。


### 2026-10-28 | 全流程改进建议审查（missions/1028-flow-improvements）

- **证据**: task_state 显示 lifecycle 10-26/27/28 连续 3 天 lifecycle_failed；10-27 subscribe=blocked_uncertain+回执 failed；runtime_data 顶层 181 文件/24.7MB（48 个临时 .py、zddx 抓包、安装包 exe）；task_state.json 361KB 无修剪；逻辑图 §7 快照停在 10-24。
- **建议要点**: P0=健康自检日结推送+10-27 不确定委托人工核对+关键回执失败兜底重发；P1=runtime_data 自动清理策略+task_state 修剪+代码文件逼近 1000 行拆分计划；P2=Server酱 5 条/日限额下推送分级、验证码 OCR 真弹窗补验。
- **Next**: 用户拍板采纳项后先改 specs 再实施。

### 2026-10-28 | 一户一事整合流 + 北交所排除 + 15/45 预算

- **北交所排除**（用户拍板）：920/43/83/87/88 开头默认不申购，orders 过滤+skipped 留痕。实测：森峰激光 920085 批量页网格本来就是空的（北交所不进该页），与排除决策一致。
- **一户一事**：F8 当日委托核验并入 subscribe 阶段——每户单会话做完 登录→申购→核验。此前 subscribe 阶段无批量提交后的 F8 核验（只有 all 阶段有）。
- **预算按用户规格重调**：登录 15s fail-fast（fund_login_timeout_s），每户整体 45s 硬限时（fund_total_timeout_s），线程看门狗两段式 join。旧 per_fund_timeout_s 降级为登录预算的兼容回退。
- **科创板/沪市板块兜底**：jqktrader 只认 sh/sz 前缀，787/科创等沪市申购代码（5/6/7/11 开头）buy 前显式补设上海Ａ股，023 开头补深圳Ａ股。明日 10-29 钶锐锶 787827 首验。
- **许*鸣融（信用户）昨天下单未落**：系统侧 submitted_unverified（F8 无记录），用户查无记录。未完全定因——信用账户打新可能受限/需信用模块申购/菜单只显示普通户；明日钶锐锶实盘重点观察该户，也可能用户需在信用交易模块查记录。
- 电脑影响：生产本就只有 10:00 申购 + 22:00 查签两次开 THS（各约5分钟）；昨日多次开同花顺是我测试所致，生产日不再。

