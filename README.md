# MyBMO — 百度电商营销官

**WorkBuddy 插件**（Agent 型专家包）· 面向电商商家的百度营销操盘手，覆盖搜索推广、信息流与 DPA、百度优选与本地 O2O 全场景，目标是把「流量 → 加购 → 支付」全链路效率做上去，并守住健康的 ROAS。

内置 `baidu-marketing-api` 技能，直连百度营销开放平台取**真实**关键词数据（搜索量 / 竞争度 / 推荐出价），不再凭经验估数字。

<p>
  <img alt="WorkBuddy Plugin" src="https://img.shields.io/badge/WorkBuddy-Plugin-1f6feb?style=flat-square">
  <img alt="Version" src="https://img.shields.io/badge/version-1.7.3-2ea043?style=flat-square">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.x-3776ab?style=flat-square&logo=python&logoColor=white">
  <img alt="Dependencies" src="https://img.shields.io/badge/dependencies-0-brightgreen?style=flat-square">
</p>

> Baidu e-commerce marketing expert packaged as a WorkBuddy plugin. Turns product images into ready-to-import keyword groups backed by real search volume and recommended bids from the Baidu Marketing Open Platform API — with multi-account support and zero third-party dependencies.

---

## 这是什么

| 项 | 值 |
|---|---|
| 载体 | WorkBuddy 插件（专家包） |
| 插件名 | `mybmo-baidu-ecommerce-marketing` |
| 类型 | `agent`（单个 AI 专家，非多角色团队） |
| 版本 | `1.7.3` |
| 分类 | `05-MarketingGrowth` |
| 包含 | 1 个 Agent（`MyBMO`）+ 1 个 Skill（`baidu-marketing-api`） |
| 运行时 | Python 3 标准库，**零第三方依赖** |

装进 WorkBuddy 后，在专家中心选中 **MyBMO** 即可对话；它会在需要取数时自动调用内置技能，不需要你手动敲命令。

## 它解决什么问题

| 常见做法 | MyBMO 的做法 |
|---|---|
| 凭经验说「这个词挺热」 | 调关键词规划师，给出 `pv` / `competition` / `rec_bid` 三个数 |
| 商品图看完靠感觉列词 | 读图提产品档案 → 拓词 → 筛词 → 四组 → 优先级 → 否词，产出词表并可直接写进账户 |
| 多账户手动切换、数据串台 | 一个 alias = 一个账户 = 一份独立凭据，报数必须带账户名 |
| 跨账户复制投放靠手工重建 | `transfer describe` 导出 → 人工核对 → `transfer clone --execute` 逐级重建 |
| 建议停在聊天里，落地还要手工敲后台 | 预览报文 → `--execute` 直接写入，全程落审计 |

## 核心能力

- **搜索推广与关键词策略**：品牌词 / 品类词 / 场景长尾词三级体系，冷启动与成熟期的匹配模式、出价系数、oCPC 节奏。
- **信息流与 DPA**：素材法则、商品库结构化上传、DPA 商品组划分。
- **百度优选与电商闭环**：慧播星、百斗天枢，618 / 双 11 分阶段预算。
- **本地店铺会员（O2O）**：地图围栏定向、门店活动获客。
- **数据诊断与复盘**：ROAS、加购转化率、ACOS、品牌回搜率为核心，按 SKU 给动作。
- **按图出词包**：读图提取卖点 → 真实搜索量批量拓词 → 按四个投放方向分组，产出词表 / 数据附表 / 优先级与否词。
- **真实数据拉取**：关键词拓词、账户数据、跨账户投放复制。
- **写操作落地**：加词、改出价与匹配模式、启停计划/单元、调预算。**默认 dry-run**，加 `--execute` 才真正写入，每次写入都落审计。
- **合规提示**：类目资质、落地页与商品库同步风险、小预算测试前置建议。

## 安装

把仓库放到 WorkBuddy 的专家市场目录（`my-experts` 是本地市场，往里放东西即视为发布）：

```bash
TARGET=~/.workbuddy/plugins/marketplaces/my-experts/plugins/mybmo-baidu-ecommerce-marketing

# 目标目录不存在时直接 clone
git clone https://github.com/bianzhishui/mybmo-baidu-ecommerce-marketing.git "$TARGET"

# 目录已存在（装过旧版）时，先备份再替换
[ -d "$TARGET" ] && mv "$TARGET" "${TARGET}.bak"
git clone https://github.com/bianzhishui/mybmo-baidu-ecommerce-marketing.git "$TARGET"
```

然后在 WorkBuddy 中刷新专家市场，专家列表里会出现 **MyBMO / 百度电商营销官**。

首次使用需要接入百度营销账户，完整流程（环境检查 → 创建应用 → 拿 authCode → 接入验证 → 权限域对照 → 故障排查）见
[`references/onboarding.md`](skills/baidu-marketing-api/references/onboarding.md)。

## 快速开始

```bash
cd ~/.workbuddy/plugins/marketplaces/my-experts/plugins/mybmo-baidu-ecommerce-marketing/skills/baidu-marketing-api

# 1. 自检：有没有已授权账户
python3 scripts/bmctl.py accounts list

# 2. 拓词
python3 scripts/bmctl.py kr expand --seed "月季" --limit 20 --format md

# 3. 多账户时指定账户
python3 scripts/bmctl.py --account axd kr expand --seed "猫粮"
```

## 命令清单

`--format` 可写在任意位置；`--dry-run` 只打印报文不发请求。

| 命令 | 用途 |
|---|---|
| `accounts list` / `use` / `remove` | 多账户管理 |
| `auth link --app-id X --callback Y` | 生成授权链接 |
| `auth serve --app-id X --developer-uid Y` | 起回调服务接住 authCode |
| `auth exchange --code Z` | 用授权码换令牌 |
| `kr expand --seed "月季" --limit 30` | 单种子词拓词，按搜索量降序 |
| `kr expand --seed "月季" --summary` | 只要聚合统计（总量 / 均价 / 竞争度） |
| `kr multi --seeds "化毛片,化毛膏"` | 多种子词拓词并按词去重 |
| `account info` / `account balance` | 账户信息 / 余额 |
| `transfer describe --from-account A` | 从 A 账户导出投放结构 |
| `transfer clone --from-account A --to-account B` | 跨账户复制投放方案 |
| `write word-add --adgroup-id 9 --words "月季,玫瑰花"` | 加词（可带出价与匹配模式） |
| `write word-update --items '[...]'` | 改关键词出价 / 匹配 / 启停 |
| `write word-delete --word-ids 11,22` | 按 id 删词 |
| `write campaign-update --campaign-id 1 --budget 300` | 改计划预算 / 启停 |
| `write adgroup-update --adgroup-id 9 --price 2.5` | 改单元出价 / 启停 |
| `call --service X --method y --body '{...}'` | 通用透传任意接口（写类方法同样要 `--confirm`） |

`write` 与 `transfer clone` 都是**两步审批**：先预览拿 `digest`，再带 digest 执行。
只加 `--execute` 不带 `--confirm` 会被拒绝（退出码 4）——这是命令层面的强制，不靠自觉。

```bash
# 1. 预览：打印 URL、报文（令牌已脱敏）与 approval.digest
python3 scripts/bmctl.py write word-add --adgroup-id 10086 \
  --words "月季,玫瑰花" --price 3.5 --phrase-type 2
# → "approval": { "digest": "cfa5cd773f5bdf99", ... }

# 2. 把报文给用户核对，确认后用那个 digest 执行
python3 scripts/bmctl.py write word-add --adgroup-id 10086 \
  --words "月季,玫瑰花" --price 3.5 --phrase-type 2 \
  --execute --confirm cfa5cd773f5bdf99
```

digest 是报文内容的指纹：没预览就拿不到，预览后改了参数（哪怕只改一个出价）也会失效。
执行被拒时**不会**回显正确 digest，避免被直接抄走绕过审批。

确认环节由**预览输出自带的卡片内容**驱动：`approval.confirm_card` 里有标题、字段
（账户 / 动作 / 条数 / 回执）、选项（确认执行 / 取消）与不可逆提示，原样弹出即可。
三条写路径——`write` 全部子命令、`transfer clone`、`call` 写类方法——都会带这张卡片。

透传时方法名支持小写蛇形，脚本自动转驼峰：

```bash
python3 scripts/bmctl.py call --service krService --method get_kr_by_query \
  --body '{"query":"多肉"}' --format md
```

### 结果字段

| 字段 | 含义 | 怎么用 |
|---|---|---|
| `pv` | 日均搜索量 | 判断词量天花板，优先吃高 pv |
| `pc_pv` / `mobile_pv` | PC / 移动分端搜索量 | 移动占比高的词，落地页要过移动端 |
| `competition` | 竞争度 | 越高抢位越贵，冷启动避开高竞争 |
| `rec_bid` | 推荐出价（元） | 出价基准，实际按位置系数上浮 |
| `group` | 百度自带归类 | 仅参考，不要当分组依据 |

## 按图出词包

给一张或多张商品图，自动走
[`keyword-sop.md`](skills/baidu-marketing-api/references/keyword-sop.md) 七步：

```
读图提产品档案 → 生成 8–12 个种子词 → kr multi 拓词
→ 筛词 → 分四组 → 排优先级 → 定否词 → 出三件套
```

三条硬约束：

1. 每个词都要能在 KR 原始返回里找到，抽查 10 个，有一个对不上就重跑。
2. 每组 20–40 词，单产品 80–130 词；不足说明种子词不够宽，超出说明筛松了。
3. 优先级理由必须带搜索量和均价，「意图精准」不算理由。

## 多账户

一个 **alias = 一个推广账户 = 一份独立凭据**，令牌互不通用，存放在
`~/.workbuddy/baidu-marketing/accounts/<alias>.json`（权限 600），**不随插件分发**，每台机器需单独授权一次。

三个必须知道的细节：

1. `user_name` 必须是该账户自己的中文名，与令牌一一对应。填错报 `81020`。
2. 多应用（账户分属不同 AppID / SecretKey）用 `--apps-file apps.json` 一次加载，**alias 必须全局唯一**。
3. 令牌有效期：accessToken 24 小时（自动续），refreshToken 30 天（到期必须重新授权）。

完整技术细节见 [`auth.md`](skills/baidu-marketing-api/references/auth.md)。

## 能力边界

权限取决于应用申请了哪些域，不是插件决定的：

| 能力 | 所需权限域 |
|---|---|
| 关键词拓词、搜索量、推荐出价 | 工具 |
| 账户信息、余额、付款 | 账户管理 |
| 计划 / 单元 / 关键词 / 创意 读写 | 投放管理 |
| 报告中心、数据下载 | 报告 |

未开通返回 `89406`，`position=_user`——**这不是令牌坏了**，同一个令牌能正常拓词。补开权限后必须重新授权。

**既能读也能写**：拓词、账户数据、结构导出是读；加词、改价、启停、改预算、跨账户复制是写。
写操作默认 dry-run，`--execute` 才发请求，每次真实写入都落审计。

写能力**强依赖「投放管理」权限域**。只有「工具」域时读接口正常、写接口一律 `89406`——
「拓词能跑」不代表「能改账户」，这两件事不要混着说。

## 错误速查

| code | 原因 | 处理 |
|---|---|---|
| `8002` | 鉴权放错位置 | 必须放请求体 JSON 的 header，不是 HTTP 头（脚本已处理） |
| `81020` | userName 与令牌不属同一账户 | 用 `--account` 指定，别手工混用凭据 |
| `89406` | 权限域未开通 | 见上节，不是令牌问题 |

错误统一以 JSON 返回，含 `code` / `position` / `hint`，退出码非 0。

## 目录结构

```
mybmo-baidu-ecommerce-marketing/
├── .codebuddy-plugin/plugin.json   # 插件元信息（版本、分类、Agent/Skill 入口）
├── agents/MyBMO.md                 # 专家人设：能力、数据工具、SOP、边界
├── skills/baidu-marketing-api/
│   ├── SKILL.md                    # 能力入口：自检、命令、字段、边界
│   ├── references/
│   │   ├── keyword-sop.md          # 图片转投流关键词的 SOP（Agent 用）
│   │   ├── auth-sop.md             # 鉴权的交互 SOP（Agent 用）
│   │   ├── auth.md                 # 鉴权技术细节与多账户
│   │   ├── onboarding.md           # 全新电脑上手（给人看）
│   │   └── api-index.md            # 133 服务 / 389 接口索引
│   └── scripts/
│       ├── bmctl.py                # CLI 薄壳
│       └── bmclient/               # 核心库（纯标准库）
│           ├── config.py           # 多账户凭据解析
│           ├── auth.py             # 令牌刷新 / 授权码换取
│           ├── oauthserver.py      # 内置回调服务
│           ├── approval.py         # 写操作审批指纹（预览 → digest → 执行）
│           ├── transport.py        # HTTP + 鉴权 + 重试
│           ├── errors.py           # 错误码释义
│           ├── render.py           # JSON / Markdown 输出
│           └── services/           # kr 拓词 / account 账户 / transfer 跨账户复制 / write 写操作
├── tests/                          # pytest：渲染 / 错误码 / 凭据 / CLI 冒烟
├── tools/build-zip.sh              # 一键生成可上传到开发平台的 zip
├── pyproject.toml                  # uv 项目配置（虚拟项目，dev 依赖 pytest、ruff）
├── uv.lock                         # 开发依赖锁文件
├── .python-version                 # 锁定 Python 3.13
├── avatars/expert.png
└── README.md
```

## 本地开发

用 `uv` 管理开发环境。**运行时零依赖**——插件由 WorkBuddy 用系统 `python3` 直接执行 `bmctl.py`，
不经过安装；`pytest` / `ruff` 只在开发时用。

```bash
uv sync                 # 创建 .venv 并装开发依赖（按 uv.lock）
uv run pytest           # 97 个用例：渲染、错误码、凭据、写操作报文、跨账户 id 链、CLI 冒烟
uv run ruff check .     # 规则集见 pyproject.toml
uv run ruff format .    # 可选，会重排未格式化的文件
```

测试通过 `BM_HOME` 环境变量把凭据目录重定向到临时目录，**不会读写你真实的
`~/.workbuddy/baidu-marketing/`**。

> `pyproject.toml` 标了 `package = false`（虚拟项目）：不打包、不安装。
> 因为插件靠 `bmctl.py` 里的 `sys.path` 注入加载 `bmclient`，加 build-system 反而会
> 让「零依赖」的承诺变形。

改完源码后，需要同步到 WorkBuddy 的插件目录并让缓存重建才能生效：

```bash
# 1. 同步到专家市场目录
rsync -a --delete \
  --exclude .git --exclude .gitignore --exclude .workbuddy --exclude .DS_Store \
  ./ ~/.workbuddy/plugins/marketplaces/my-experts/plugins/mybmo-baidu-ecommerce-marketing/

# 2. 递增 .codebuddy-plugin/plugin.json 里的 version，再在 WorkBuddy 中重新安装该专家
```

> 运行时真正加载的是 `~/.workbuddy/plugins/cache/my-experts/mybmo-baidu-ecommerce-marketing/<version>/`，
> 只改市场源不升版本号，缓存不会重建。

## 打包上传到开发平台

```bash
./tools/build-zip.sh
# → dist/mybmo-baidu-ecommerce-marketing.zip   （22 个文件，约 500 KB）
```

脚本走的是 WorkBuddy 官方 `expert-manager` 的四步流程：

```
同步 → 校验（validate_expert.py）→ 注册（register_expert.py）→ 打包（package_expert.py）
```

**为什么要先"同步"**：官方校验器强制要求专家目录位于
`$WORKBUDDY_CONFIG_DIR/plugins/marketplaces/my-experts/plugins` 下，
直接对本仓库目录打包会被判为"专家不在专家目录下"而失败。脚本会先同步一份干净的
运行时副本过去，再对它校验和打包。

**包里有什么**：`plugin.json`、`README.md`、`agents/`、`avatars/`、`skills/`。
开发用文件不会进包——`tests/`、`tools/`、`pyproject.toml`、`uv.lock`、`.venv`、`.git`。
注意排除规则用前导斜杠锚定（`/tools` 而非 `tools`），否则会误伤
`skills/baidu-marketing-api/scripts` 这类同名嵌套目录。

zip 内部结构是单个顶层目录，上传时不要额外套壳：

```
mybmo-baidu-ecommerce-marketing/
├── .codebuddy-plugin/plugin.json
├── agents/MyBMO.md
├── avatars/expert.png
├── skills/baidu-marketing-api/...
└── README.md
```

**上传前要做的**：递增 `.codebuddy-plugin/plugin.json` 的 `version`，
并与 `pyproject.toml`、README 徽章保持一致（同名同版本重复上传通常会被拒）。

如果 `expert-manager` 不在默认安装路径，用环境变量指定：

```bash
EXPERT_MANAGER_DIR=/path/to/skills/expert-manager/scripts ./tools/build-zip.sh
```

## 安全与隐私

- **凭据不入库**：令牌只存在本机 `~/.workbuddy/baidu-marketing/accounts/`，`.gitignore` 已排除 `accounts/`、`*.token`、`.env`。
- **运行时零依赖**：纯 Python 标准库，不引入任何外部包（`pytest` / `ruff` 仅开发时使用），减少供应链面。
- **写操作强制两步审批**：预览拿 digest 才能执行，没预览或报文被改过一律拒绝（退出码 4）；权限不足时本地拦截（退出码 3），不发出半截请求。
- **写操作留痕**：每次真实写入追加到 `~/.workbuddy/baidu-marketing/audit/YYYY-MM-DD.jsonl`，含账户、动作、物料、完整报文与审批 digest，出问题可按天回溯。
- **批量有上限**：单次 200 词 / 20 计划 / 50 单元，超限直接拒绝而不是替你分批跑——改太多出错时无法人工核对。
- **回调服务只监听 `127.0.0.1`**，公网靠隧道转发，不做 AES 验签而改为校验 state 的 base 部分。

## 免责声明

- 不保证具体 ROAS 或成本数字，只给行业参考区间与验证方法。
- 所有策略建议基于百度营销公开可查的产品逻辑，不虚构后台不存在的按钮或入口；功能以账户后台实际展示为准。
- 涉及医疗、保健、金融等强监管类目，先提示资质与审核风险，再谈投放策略。
- 任何投放金额建议都应先小预算测试模型，跑通后再逐步放量。

## 许可

本仓库暂未附带 LICENSE 文件。如需对外分发，建议先补充许可证声明。
