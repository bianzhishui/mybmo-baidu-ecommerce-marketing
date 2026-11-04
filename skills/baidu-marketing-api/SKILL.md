---
name: baidu-marketing-api
description: |
  百度营销开放平台数据能力：多账户管理（一个 alias 一个推广账户，切换账户与令牌刷新）、
  关键词规划师拓词（搜索量/竞争度/推荐出价）、按商品图产出可投流的关键词分组方案、
  账户与余额查询、跨账户复制投放方案（把 A 账户的计划/关键词/创意在 B 账户重建）、
  以及任意百度营销接口的通用透传调用。
  当需要真实关键词数据、多账户数据、或把某账户的投放复制到另一账户时使用。
  触发词：关键词拓词、关键词规划师、拉取关键词数据、按图拓词、图片转关键词、投流词包、
  关键词分组、投流分组、多账户、切换账户、账户列表、账户余额、跨账户复制、投放复制、
  搬投放、百度营销API、百度推广接口、搜索量、竞争度、推荐出价。
description_en: |
  Baidu Marketing Open Platform data access with multi-account support: manage several ad
  accounts by alias with independent credentials, keyword planning (search volume, competition,
  recommended bids), turning product images into ready-to-launch keyword groups, account and
  balance queries, cross-account campaign cloning, and a generic passthrough for any Baidu
  Marketing API endpoint. Use when real keyword data, multi-account data, or copying a campaign
  from one account to another is needed.
---

# 百度营销 API 数据能力

把「凭经验估」换成「用真实数据算」。所有关键词结论都应基于关键词规划师返回的
搜索量、竞争度、推荐出价，而不是凭空给数字。

底层是纯标准库实现的 Python 客户端，零第三方依赖。

## 零、首次自检

涉及取数时，先跑这一条：

```bash
python3 scripts/bmctl.py accounts list
```

- 有账户且 `usable: true` → 直接干活，用户不关心鉴权
- 提示"还没有任何已授权账户" → **不要反复重试业务命令**，按 `references/auth-sop.md` 引导
- 报 Python 错误 → 环境问题，不是权限问题

凭据不随专家包分发，每台机器需单独授权一次。

## 一、多账户与授权

一个 **alias = 一个推广账户 = 一份独立凭据**，令牌互不通用。

```bash
python3 scripts/bmctl.py accounts list                          # 看有哪些账户
python3 scripts/bmctl.py accounts use wds02                     # 设默认账户
python3 scripts/bmctl.py --account axd kr expand --seed "猫粮"   # 指定账户执行
python3 scripts/bmctl.py --account axd auth status              # 查令牌状态
```

接入账户用内置回调服务，**一次可连续接多个**：

```bash
# 起服务（默认不限账户数，持续到 --wait 超时）
python3 scripts/bmctl.py auth serve --port 8080 \
  --app-id <AppID> --developer-uid <开发者uid> --secret-key <SecretKey> --wait 900

# 为每个账户生成带别名的链接，分头发出去
python3 scripts/bmctl.py auth link --app-id <AppID> --developer-uid <开发者uid> \
  --callback https://<公网地址>/oauth/callback --alias acc_a
```

别名编进 `state`（格式 `{base}.{alias}`），服务据此决定令牌存到哪个账户。
服务只监听 `127.0.0.1`，公网靠隧道转发；不做 AES 验签，改为校验 state 的 base 部分。

凭据落在 `~/.workbuddy/baidu-marketing/accounts/<alias>.json`（权限 600）。
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
| `call --service X --method y --body '{...}'` | 通用透传任意接口 |

透传时方法名支持小写蛇形，脚本自动转驼峰：

```bash
python3 scripts/bmctl.py call --service krService --method get_kr_by_query \
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
python3 scripts/bmctl.py transfer describe --from-account wds02 --campaign-ids 123 --out plan.json

# 2. 人工核对 plan.json：价格、地域、落地页、否定词、时段

# 3. 预览在 B 将执行的动作
python3 scripts/bmctl.py transfer clone --plan-file plan.json --to-account axd --prefix "A-"

# 4. 确认后写入（需要投放管理权限）
python3 scripts/bmctl.py transfer clone --plan-file plan.json --to-account axd --prefix "A-" --execute
```

三条硬规则：

1. **id 必须剔除**。计划/单元/关键词的 id 是账户内唯一的，带到 B 会写到错误物料上。
   导出和写入各 strip 一次，双重保险。
2. **名字带来源标记**。`--prefix` 同时改外层 `name` 和 config 里的 `*Name`，否则会出现
   "预览带前缀、实际创建不带"的错位。
3. **写操作默认关闭**。不加 `--execute` 只打印；权限不足时会被本地拦住（退出码 3），
   不会打出半截请求污染目标账户。

## 六、能力边界

权限取决于应用申请了哪些域，不是专家决定的：

| 能力 | 所需权限域 |
|---|---|
| 关键词拓词、搜索量、推荐出价 | 工具 |
| 账户信息、余额、付款 | 账户管理 |
| 计划/单元/关键词/创意 读写 | 投放管理 |
| 报告中心、数据下载 | 报告 |

未开通返回 `89406 The access token ... invalidate`，`position=_user`。
**这不是令牌坏了**——同一个令牌能正常拓词。补开权限后必须重新授权，旧令牌不会自动获得新权限。

**本能力的定位是"读数据、算策略"**，写操作（改价、建计划）必须由人在后台执行。

## 七、错误速查

| code | 原因 | 处理 |
|---|---|---|
| 8002 | 鉴权放错位置 | 必须放请求体 JSON 的 header，不是 HTTP 头（脚本已处理） |
| 81020 | userName 与令牌不属同一账户 | 用 `--account` 指定，别手工混用凭据 |
| 89406 | 权限域未开通 | 见上节，不是令牌问题 |

错误统一以 JSON 返回，含 `code` / `position` / `hint`，退出码非 0。
完整错误码表见 `references/auth.md`。

## 八、给分析人员的建议

1. **先拓词再谈策略**：拿到 `pv` 和 `rec_bid` 再排序级，不要凭感觉说"这个词热"。
2. **窄词返回少**：百度对长尾窄词返回量小，用品类词才能拿到几百条。
3. **结果要落盘**：拓词结果存 JSON/CSV 再分析，不要只留在对话里。
4. **推荐出价只是起点**：实际出价 = 推荐出价 × 排名系数 × 时段/地域系数。

接口索引见 `references/api-index.md`。
