---
name: baidu-marketing-api
version: "1.9.2"
description: |
  百度营销开放平台数据能力：多账户管理（一个 alias 一个推广账户，切换账户与令牌刷新）、
  关键词规划师拓词（搜索量/竞争度/推荐出价）、按商品图产出可投流的关键词分组方案、
  账户与余额查询、跨账户复制投放方案（把 A 账户的计划/关键词/创意在 B 账户重建）、
  写操作（加词、改出价与匹配模式、启停计划/单元、调预算，默认 dry-run）、
  以及任意百度营销接口的通用透传调用。
  当需要真实关键词数据、多账户数据、把某账户的投放复制到另一账户、或把方案真正写进账户时使用。
  触发词：关键词拓词、关键词规划师、拉取关键词数据、按图拓词、图片转关键词、投流词包、
  关键词分组、投流分组、多账户、切换账户、账户列表、账户余额、跨账户复制、投放复制、
  搬投放、加词、添加关键词、改出价、调价、暂停计划、启用计划、调预算、写操作、
  百度营销API、百度推广接口、搜索量、竞争度、推荐出价。
description_en: |
  Baidu Marketing Open Platform access with multi-account support: manage several ad
  accounts by alias with independent credentials, keyword planning (search volume, competition,
  recommended bids), turning product images into ready-to-launch keyword groups, account and
  balance queries, cross-account campaign cloning, write operations (add keywords, change bids
  and match types, pause or enable campaigns and adgroups, adjust budgets — dry-run by default),
  and a generic passthrough for any Baidu Marketing API endpoint. Use when real keyword data,
  multi-account data, copying a campaign between accounts, or actually applying changes to an
  account is needed.
---

# 百度营销 API 数据能力

把「凭经验估」换成「用真实数据算」。所有关键词结论都应基于关键词规划师返回的
搜索量、竞争度、推荐出价，而不是凭空给数字。

由 **`uv` 执行**，运行时依赖声明在脚本头部的内联元数据里：
`uv` 读脚本头部的内联元数据（PEP 723）自动准备隔离环境并选解释器，三平台同一条命令。

## 零、首次自检

### 先确认 uv 可用

```bash
uv --version
```

- 三平台**同一条命令**，不再有 `python3` / `py -3` 的选择题
- 报 `command not found` / `'uv' 不是内部或外部命令`（退出码 127）= 没装 uv。
  把官方安装命令给用户执行，**不要替他装，也不要改用 `pip install` 装依赖**
  - macOS / Linux：`curl -LsSf https://astral.sh/uv/install.sh | sh`
  - Windows：`powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
- 通了以后，本会话所有调用统一写成 `uv run <技能目录>/scripts/bmctl.py <子命令>`；
  路径含空格时整体加引号

三个使用细节：

1. **首次运行慢几秒**是在建隔离环境（缓存在 `uv cache dir`，之后复用），不是卡死。
   uv 的进度提示走 **stderr**，脚本的 JSON 走 **stdout**——别把 stderr 当错误。
2. **参数位置**：`uv` 自己的选项只能写在脚本路径**之前**，路径之后的参数全归脚本。
   `uv run --help` 是 uv 的帮助，`uv run bmctl.py --help` 才是本工具的。
3. **降级**：仅当 uv 装不上、且机器已有 Python 3.9+ 时才用 `python3 <路径>/scripts/bmctl.py`，
   行为完全一致。**退出码 6 只会出现在这条降级路径上**。

### 再检查账户

涉及取数时，先跑这一条：

```bash
uv run scripts/bmctl.py accounts list
```

- 有账户且 `usable: true` → 直接干活，用户不关心鉴权
- 提示"还没有任何已授权账户" → **不要反复重试业务命令**，按 `references/auth-sop.md` 引导
- 提示 uv 命令不存在 → 按上面的安装指引走，**不要换参数重试**
- 退出码 6 → 绕过了 uv 直接调了低版本 python，改用 `uv run` 即可
- 其它 Python 报错 → 环境问题，不是权限问题

凭据不随专家包分发，每台机器需单独授权一次。运行方式与 uv 安装命令见 `runtime.json`；
依赖与 Python 下限以脚本头部内联元数据为准。

## 一、多账户与授权

一个 **alias = 一个推广账户 = 一份独立凭据**，令牌互不通用。

```bash
uv run scripts/bmctl.py accounts list                          # 看有哪些账户
uv run scripts/bmctl.py accounts use wds02                     # 设默认账户
uv run scripts/bmctl.py --account axd kr expand --seed "猫粮"   # 指定账户执行
uv run scripts/bmctl.py --account axd auth status              # 查令牌状态
```

接入账户用内置回调服务，**一次可连续接多个**：

```bash
# 起服务（默认不限账户数，持续到 --wait 超时）
uv run scripts/bmctl.py auth serve --port 8080 \
  --app-id <AppID> --developer-uid <开发者uid> --secret-key <SecretKey> --wait 900

# 为每个账户生成带别名的链接，分头发出去
uv run scripts/bmctl.py auth link --app-id <AppID> --developer-uid <开发者uid> \
  --callback https://<公网地址>/oauth/callback --alias acc_a
```

别名编进 `state`（格式 `{base}.{alias}`），服务据此决定令牌存到哪个账户。
服务默认只监听 `127.0.0.1`，公网靠隧道转发；容器/反代场景可显式 `--host 0.0.0.0`，
此时 CLI 会打印警告。不做 AES 验签，改为校验 state 的 base 部分。

凭据落在 `~/.workbuddy/baidu-marketing/accounts/<alias>.json`
（macOS/Linux 权限 600；Windows 无 POSIX 权限位，靠用户目录 ACL，默认仅本人可读）。
`BM_ACCOUNT` 可临时指定账户，`BAIDU_*` 环境变量优先级最高。

### 三个必须知道的细节

1. **`user_name` 必须是该账户自己的中文名**，与令牌一一对应。填错报 `81020`，
   这是多账户最典型的错误，别手工混用凭据。
2. **多应用**（账户分属不同 AppID / SecretKey）用 `--apps-file apps.json` 一次加载，
   不要为每个应用起一个服务。**alias 必须全局唯一**，跨应用同名会覆盖。
3. **state 是否原样回传尚未实证**。解析不出别名时按 `acct_<userId>` 兜底，
   输出里的 `alias_source` 字段告诉你实际走了哪条路。

令牌有效期：accessToken 24 小时（自动续），refreshToken 30 天（到期必须重新授权）。
`access_expired: true` 不用管，`refresh_expired: true` 才是真问题。

> 完整的技术细节（授权流程、apps.json 格式、错误排查）见 `references/auth.md`；
> 需要带着用户一步步走授权流程时，按 `references/auth-sop.md` 执行。

## 二、命令清单

脚本在 `scripts/` 下，用本技能的 base directory 拼绝对路径执行。
`--format` 可写在任意位置；`--dry-run` 只打印报文不发请求。

| 命令 | 用途 |
|---|---|
| `accounts list` / `use` / `remove` | 多账户管理 |
| `auth link --app-id X --callback Y` | 生成授权链接 |
| `auth serve --app-id X --developer-uid Y` | 起回调服务接住 authCode |
| `auth exchange --code Z` | 用授权码换令牌 |
| `kr expand --seed "月季" --limit 30` | 单种子词拓词，按搜索量降序 |
| `kr expand --seed "月季" --summary` | 只要聚合统计（总量/均价/竞争度） |
| `kr multi --seeds "化毛片,化毛膏"` | 多种子词拓词并按词去重 |
| `account info` / `account balance` | 账户信息 / 余额 |
| `transfer describe --from-account A` | 从 A 账户导出投放结构 |
| `transfer clone --from-account A --to-account B` | 跨账户复制投放方案 |
| `write word-add --adgroup-id 9 --words "月季,玫瑰花"` | 加词（可带价与匹配模式） |
| `write word-update --items '[...]'` | 改关键词出价 / 匹配 / 启停 |
| `write word-delete --word-ids 11,22` | 按 id 删词 |
| `write campaign-update --campaign-id 1 --budget 300` | 改计划预算 / 启停 |
| `write adgroup-update --adgroup-id 9 --price 2.5` | 改单元出价 / 启停 |
| `call --service X --method y --body '{...}'` | 通用透传任意接口（写类方法同样要 `--confirm`） |

透传时方法名支持小写蛇形，脚本自动转驼峰：

```bash
uv run scripts/bmctl.py call --service krService --method get_kr_by_query \
  --body '{"query":"多肉"}' --format md
```

## 三、拓词结果的字段含义

| 字段 | 含义 | 怎么用 |
|---|---|---|
| `pv` | 日均搜索量 | 判断词量天花板，优先吃高 pv |
| `pc_pv` / `mobile_pv` | PC / 移动分端搜索量 | 移动占比高的词，落地页要过移动端 |
| `competition` | 竞争度 | 越高抢位越贵，冷启动避开高竞争 |
| `rec_bid` | 推荐出价（元） | 出价基准，实际按位置系数上浮 |
| `group` | 百度自带归类 | 仅参考，不要当分组依据 |
| `reasons` | 推荐原因 | 解释为什么返回这个词 |

`--summary` 输出的 `bid_avg` / `competition_avg` 可直接判断这组词该不该投。

## 四、按图产出关键词（走 SOP）

用户给商品图、要求拓词或做投流分组时，**不要临时发挥**，按 `references/keyword-sop.md` 执行：
读图提产品档案 → 生成 8–12 个种子词 → `kr multi` 拓词 → 筛词 → 四组 → 优先级 → 否词 → 三件套产出。

最容易错的三点：

- **种子词用最短的品类词根。** 产品全名反而窄：「体外驱虫喷雾」只回 50 条，「宠物驱虫」回 300 条。
- **必须剔跨品类和器械工具词。** 这两类搜索量不低但点了不买，是最烧钱的部分。
- **优先级理由必须带数字。** 「意图精准」这种话不算理由。

## 五、跨账户复制

场景：A 账户里某个商品的整套投放结构，在 B 账户复制一份。**默认全程只打印、不写入**：

```bash
# 1. 从 A 导出（已剔除所有 id）
uv run scripts/bmctl.py transfer describe --from-account wds02 --campaign-ids 123 --out plan.json

# 2. 人工核对 plan.json：价格、地域、落地页、否定词、时段

# 3. 预览在 B 将执行的动作
uv run scripts/bmctl.py transfer clone --plan-file plan.json --to-account axd --prefix "A-"

# 4. 确认后写入（需要投放管理权限）
uv run scripts/bmctl.py transfer clone --plan-file plan.json --to-account axd --prefix "A-" --execute
```

三条硬规则：

1. **id 必须剔除**。计划/单元/关键词的 id 是账户内唯一的，带到 B 会写到错误物料上。
   导出和写入各 strip 一次，双重保险。
2. **名字带来源标记**。`--prefix` 同时改外层 `name` 和 config 里的 `*Name`，否则会出现
   "预览带前缀、实际创建不带"的错位。
3. **写操作默认关闭**。不加 `--execute` 只打印；权限不足时会被本地拦住（退出码 3），
   不会打出半截请求污染目标账户。

`--execute` 时是**串行写入**：计划 → 单元 → 关键词 / 创意，每级用上一级接口返回的新 id
挂接。取不到 id 会立即中止并报错——不会猜一个 id 继续写下去，也不会静默跳过。

## 六、写操作

支持直接改账户：加词、改价、改匹配、启停、改预算。**写操作必须两步走，不能一步到位。**

### 两步审批：预览 → 拿 digest → 执行

```bash
# 第一步：预览（不带 --execute）。会打印完整报文，并给出 approval.digest
uv run scripts/bmctl.py write word-add --adgroup-id 10086 \
  --words "月季,玫瑰花" --price 3.5 --phrase-type 2
# 输出里： "approval": {"digest": "cfa5cd773f5bdf99", ...}

# 第二步：把报文给用户核对，得到明确同意后，用那个 digest 执行
uv run scripts/bmctl.py write word-add --adgroup-id 10086 \
  --words "月季,玫瑰花" --price 3.5 --phrase-type 2 \
  --execute --confirm cfa5cd773f5bdf99
```

**「把报文给用户核对」不是随手发段文字**：预览输出里的 `approval.confirm_card` 已经是
现成的卡片内容（账户 / 动作 / 条数 / 回执 / 确认执行 / 取消 / 不可逆提示），**原样弹给用户点选**。
点「确认执行」之后才走第二步。覆盖 `write` 全部子命令、`transfer clone`、`call` 写类方法三条路径。

**为什么必须有 digest**：它是报文内容的指纹。

- 没有 digest → 说明没预览过 → 直接拒绝（退出码 4）
- digest 与当前报文不符 → 说明预览之后改了参数 → 也拒绝

所以「先给用户看，再写」不是靠自觉，而是命令层面强制。digest **只会出现在预览输出里**，
执行被拒时不会回显——别想从错误信息里抄一个。

### 四条速记

1. **三步走**：预览 → 弹确认卡片 → 带 digest 执行；一次只做一件事，别把加词和改价塞进一条命令。
2. **报数带 id**：说"已加 3 个词，wordId 7001/7002/7003"，不说"已完成"。
3. **批量上限**：单次 200 词 / 20 计划 / 50 单元；超了本地拒绝，不替你分批。
4. **每次写入落审计**：`~/.workbuddy/baidu-marketing/audit/YYYY-MM-DD.jsonl`。

**完整规范**在 [`references/write-rules.md`](references/write-rules.md)：三条受约束路径、
卡片必含字段、无卡片环境怎么降级、以及失败对照表（退出码 3/4/5/2 各代表什么）。
本页只留能在任意场景独立成立的摘要。
## 七、能力边界

权限取决于应用申请了哪些域，不是专家决定的：

| 能力 | 所需权限域 |
|---|---|
| 关键词拓词、搜索量、推荐出价 | 工具 |
| 账户信息、余额、付款 | 账户管理 |
| 计划/单元/关键词/创意 读写 | 投放管理 |
| 报告中心、数据下载 | 报告 |

未开通返回 `89406 The access token ... invalidate`，`position=_user`。
**这不是令牌坏了**——同一个令牌能正常拓词。补开权限后必须重新授权，旧令牌不会自动获得新权限。

**本能力既能读也能写**：拓词、账户数据、投放结构导出是读；加词、改价、启停、改预算、
跨账户复制是写。写操作走 `write` / `transfer clone --execute`，默认 dry-run，
必须带预览得到的 `--confirm <digest>` 才发请求，且每次真实写入都落审计。

`call` 通用透传**不豁免审批**：方法名不是 `get* / query* / list* / search*` 开头的一律按写操作处理，
同样要 `--confirm`。判断不出来时按写处理——多要一次审批，好过误改账户。

写能力**强依赖「投放管理」权限域**。只有「工具」域时读接口正常、写接口一律 89406——
所以「拓词能跑」不代表「能改账户」，这两件事别混着说。

## 八、错误速查

| code / 退出码 | 原因 | 处理 |
|---|---|---|
| `8002` | 鉴权放错位置 | 必须放请求体 JSON 的 header，不是 HTTP 头（脚本已处理） |
| `81020` | userName 与令牌不属同一账户 | 用 `--account` 指定，别手工混用凭据 |
| `89406` | 权限域未开通 | 见「七、能力边界」，不是令牌问题 |
| 退出码 `6` | 绕过了 uv，直接用 <3.9 的 python | 改用 `uv run`。**不是权限问题，换参数重试没用** |

错误统一以 JSON 返回，含 `code` / `position` / `hint`，退出码非 0。
完整错误码表见 `references/auth.md`。

## 九、给分析人员的建议

1. **先拓词再谈策略**：拿到 `pv` 和 `rec_bid` 再排序级，不要凭感觉说"这个词热"。
2. **窄词返回少**：百度对长尾窄词返回量小，用品类词才能拿到几百条。
3. **结果要落盘**：拓词结果存 JSON/CSV 再分析，不要只留在对话里。
4. **推荐出价只是起点**：实际出价 = 推荐出价 × 排名系数 × 时段/地域系数。

接口索引见 `references/api-index.md`。
