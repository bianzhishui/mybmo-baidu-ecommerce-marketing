---
name: baidu-marketing-api
display_name: 百度营销数据能力
display_name_zh: 百度营销数据能力
display_name_en: Baidu Marketing Data
version: "1.10.0"
agent_created: true
description: |
  百度营销开放平台数据能力：多账户管理、关键词规划师拓词（搜索量/竞争度/推荐出价）、
  按商品图规划真实关键词分组、账户与余额查询、跨账户复制模板、写操作（默认 dry-run）
  及通用接口透传。需要真实关键词数据、多账户数据、跨账户投放方案或写进账户时使用。
  触发词：关键词拓词、关键词规划师、拉取关键词数据、按图拓词、图片转关键词、投流词包、
  关键词分组、多账户、切换账户、账户余额、跨账户复制、投放复制、加词、改出价、
  暂停计划、调预算、百度营销API、百度推广接口、搜索量、竞争度、推荐出价。
description_zh: |
  百度营销开放平台数据能力：多账户管理、关键词规划师拓词（搜索量/竞争度/推荐出价）、
  按商品图规划真实关键词分组、账户与余额查询、跨账户复制模板、写操作（默认 dry-run）
  及通用接口透传。需要真实关键词数据、多账户数据、跨账户投放方案或写进账户时使用。
  触发词：关键词拓词、关键词规划师、拉取关键词数据、按图拓词、图片转关键词、投流词包、
  关键词分组、多账户、切换账户、账户余额、跨账户复制、投放复制、加词、改出价、
  暂停计划、调预算、百度营销API、百度推广接口、搜索量、竞争度、推荐出价。
description_en: |
  Baidu Marketing Open Platform access with multi-account credentials, keyword planning,
  image-guided keyword workflows, account queries, experimental campaign-copy templates,
  dry-run-first write operations, and a generic API passthrough. Use for real keyword data,
  account data, campaign planning, or explicitly approved account changes.
---

# 百度营销 API 数据能力

用真实 API 数据替代估算。所有关键词、搜索量与出价结论必须来自实际返回；
未接入账户时只给待验证框架，不编造数字或词包。

## 一、先决定执行方式与账户

将 `<skill>` 替换为本技能目录的绝对路径；路径含空格时整体加引号。

```bash
uv run <skill>/scripts/bmctl.py accounts list
```

已有 Python 3.9+ 而没有 uv 时，直接运行同一脚本即可，无需安装依赖：

```bash
python3 <skill>/scripts/bmctl.py accounts list   # Windows 用 py -3
```

| 结果 | 处理方式 |
|---|---|
| `total > 0` 且目标账户 `usable: true` | 直接执行；多账户用 `--account <alias>` 或先 `accounts use <alias>` |
| `total: 0` | 说明真实数据暂不可得，按下方「无凭据时」回答；不要重试业务命令 |
| 只有 `source: environment` | 是临时环境凭据，可直接取数，但不能设为默认或写回 |
| `refresh_expired: true` | 重新授权；不要当作普通网络错误 |
| `usable: false` | 检查令牌与 `user_name`，不要混用不同账户的凭据 |
| uv 不存在 | 已有 Python 3.9+ 就直接运行；否则按 `references/onboarding.md` 安装 |
| 凭据 JSON 损坏 | 按错误中的路径修复；不要当成“无账户”重新覆盖 |

详细环境、授权及多应用步骤见 `references/onboarding.md`、`references/auth.md`；
与用户逐步沟通时按 `references/auth-sop.md`。

### 无凭据时：给三件事，不空转

1. **现状**：本机没有可用的百度营销授权，无法取得真实搜索量或账户数据。
2. **下一步**：先运行上面的 `accounts list`；确认需接入时，按 `references/auth-sop.md`
   一次只让用户完成一个授权步骤。`auth link` 生成的一次性链接不可复用。
3. **当前可做**：可按 `references/keyword-sop.md` 整理产品档案、种子词与待验证表格，
   或按 `references/api-index.md` 核对参数；不含虚构关键词、搜索量或出价。

## 二、核心命令

```bash
# 账户与令牌
uv run <skill>/scripts/bmctl.py accounts list
uv run <skill>/scripts/bmctl.py --account axd auth status

# 关键词：单种子 / 多种子 / 汇总
uv run <skill>/scripts/bmctl.py --account axd kr expand --seed "月季" --limit 30
uv run <skill>/scripts/bmctl.py --account axd kr multi --seeds "月季,花肥" --format json
uv run <skill>/scripts/bmctl.py --account axd kr expand --seed "月季" --summary

# 账户信息与余额
uv run <skill>/scripts/bmctl.py --account axd account info
uv run <skill>/scripts/bmctl.py --account axd account balance

# 通用接口透传
uv run <skill>/scripts/bmctl.py --account axd call --service krService \
  --method get_kr_by_query --body '{"query":"月季"}'
```

`--format json|md`、`--dry-run`、`--timeout`、`--account` 可放在顶层或最末叶子命令后。
接口请求的业务参数放在 JSON `body`；鉴权由工具放入请求体 `header`，不要手填令牌。

关键词字段：`pv` 日均搜索量、`competition` 竞争度、`rec_bid` 推荐出价（元）。
`coverage` 表示当前仅为单次 API 响应；`complete: null` 表示未证实全量。
汇总是当前返回、去重及 limit 后集合的简单算术统计，不是全量或搜索量加权。

用户给商品图并要求拓词或分组时，按 `references/keyword-sop.md`：
产品档案 → 种子词 → 真实拓词 → 筛词 → 分组 → 优先级 → 否词 → 交付。
不得把待验证种子词当成已返回关键词。

## 三、写操作：预览 → 确认 → 执行

```bash
# 1. 本地预览：不发业务请求、不刷新 OAuth、不写凭据；取得 approval.digest
uv run <skill>/scripts/bmctl.py --account axd write word-add \
  --adgroup-id 10086 --words "月季,玫瑰花" --price 3.5 --phrase-type 2

# 2. 原样向用户展示 approval.confirm_card，得到明确同意

# 3. 用本次预览的 digest 执行
uv run <skill>/scripts/bmctl.py --account axd write word-add \
  --adgroup-id 10086 --words "月季,玫瑰花" --price 3.5 --phrase-type 2 \
  --execute --confirm <digest>
```

支持 `word-add`、`word-update`、`word-delete`、`campaign-update`、`adgroup-update`。
单次上限：200 词 / 20 计划 / 50 单元 / 50 创意；超限先本地拒绝。
通用 `call` 中非 `get/query/list/search/describe/download/check` 前缀的方法一律按写处理；
审批绑定账户、报文与 product_line，旧 digest 不可复用。

真实写入按 `request_id` 记录 `attempted` 和 `succeeded/failed/unknown`。
网络中断等结果未知时，先查后台与审计，不要直接重试；写请求不会自动重发。
完整规则见 `references/write-rules.md`。

## 四、跨账户复制：当前为实验能力

```bash
# 从源账户读取结构；这一步是真实读取，可能联网
uv run <skill>/scripts/bmctl.py transfer describe \
  --from-account wds02 --campaign-ids 123 --out plan.json

# 本地预览目标账户的共享模板与 digest
uv run <skill>/scripts/bmctl.py transfer clone \
  --plan-file plan.json --to-account axd --prefix "A-"

# 只有 executable: true 时才可进入此步；人工确认后执行
uv run <skill>/scripts/bmctl.py transfer clone \
  --plan-file plan.json --to-account axd --prefix "A-" \
  --execute --confirm <digest>
```

目标行为是**所有新物料默认暂停**，保留预算、URL 等配置供用户核对。
预览的 `execution_blockers` 列出尚未取得官方写 schema 或测试证据的层级；
存在阻塞项时，`--execute` 会在发送任何请求前拒绝，不猜测暂停字段。

预览与执行共用模板，父 ID 以占位符绑定，执行时仅替换为对应父级返回的新 ID。
计划 → 单元 → 关键词 / 创意串行创建；失败会返回已创建 ID、失败步骤和审计路径。
FEED 复制写入未支持；单次响应的导出不等于全量账户结构。

## 五、错误与权限

| 错误 | 判断与动作 |
|---|---|
| `8002` | 鉴权位置错误；由工具放请求体 header，不是 HTTP 头 |
| `81020` | userName 与令牌不属同一账户；检查 `--account` |
| `89406` | 多为权限域未开通；补权限后重新授权，不要盲目刷新 |
| `87091` | 服务或方法名错误；KR 规范方法为 `getKRByQuery` |
| 退出码 2 | 参数或凭据问题；按 JSON 的 message 修复 |
| 退出码 3 | 本地权限/安全门禁拒绝，未发请求 |
| 退出码 4 | 缺审批或 digest 不匹配；重新预览 |
| 退出码 5 | 写入中断；先处理输出中的 created/current_step |
| 退出码 6 | 直接 Python 运行时版本低于 3.9；换解释器或用 uv |

关键词拓词需「工具」域；账户信息/余额需「账户管理」；计划/单元/关键词/创意读写需「投放管理」。
通用透传只负责传输、保守审批与错误结构化，不保证任意接口参数、分页或远端兼容性。
完整接口索引见 `references/api-index.md`。
