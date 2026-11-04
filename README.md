# MyBMO — 百度电商营销官

MyBMO（Baidu Marketing Officer）是面向电商商家的百度营销专家，覆盖搜索推广、信息流与 DPA、
百度优选与本地 O2O 全场景，目标是把"流量-加购-支付"全链路效率做上去，并守住健康的 ROAS。

内置 `baidu-marketing-api` 能力，可直接调百度营销开放平台拿真实关键词数据，不再凭经验估数字。

## 类型

Agent 型（单个 AI 专家）

## 功能

- **搜索推广与关键词策略**：品牌词-品类词-场景长尾词三级体系，冷启动与成熟期的匹配模式、出价系数、oCPC 节奏。
- **信息流与 DPA**：素材法则、商品库结构化上传、DPA 商品组划分。
- **百度优选与电商闭环**：慧播星、百斗天枢，618/双 11 分阶段预算。
- **本地店铺会员（O2O）**：地图围栏定向、门店活动获客。
- **数据诊断与复盘**：ROAS、加购转化率、ACOS、品牌回搜率为核心，按 SKU 给动作。
- **按图出词包**：给一张或多张商品图，自动读图提取卖点 → 用真实搜索量批量拓词 → 按四个投放方向分组，产出可导入百度后台的词表、数据附表、优先级与否词。
- **真实数据拉取**：关键词拓词（搜索量/竞争度/推荐出价）、账户数据、跨账户投放复制。
- **合规提示**：类目资质、落地页与商品库同步风险、小预算测试前置建议。

## 使用示例

- 发几张商品图，帮我出可导入百度后台的投流关键词分组
- 用我自己的百度推广账户，查这几个词的真实搜索量和推荐出价
- 帮我制定电商新品在百度搜索推广的冷启动关键词与出价策略

## 目录结构

```
mybmo-baidu-ecommerce-marketing/
├── .codebuddy-plugin/plugin.json
├── agents/MyBMO.md                # 专家人设：能力、数据工具、SOP、边界
├── skills/baidu-marketing-api/
│   ├── SKILL.md                   # 能力入口：自检、命令、字段、边界
│   ├── references/
│   │   ├── keyword-sop.md         # 图片转投流关键词的 SOP（Agent 用）
│   │   ├── auth-sop.md            # 鉴权的交互 SOP（Agent 用）
│   │   ├── auth.md                # 鉴权技术细节与多账户
│   │   ├── onboarding.md          # 全新电脑上手（给人看）
│   │   └── api-index.md           # 133 服务 / 389 接口索引
│   └── scripts/
│       ├── bmctl.py               # CLI 薄壳
│       └── bmclient/              # 核心库（纯标准库）
│           ├── config.py          # 多账户凭据解析
│           ├── auth.py            # 令牌刷新 / 授权码换取
│           ├── oauthserver.py     # 内置回调服务
│           ├── transport.py       # HTTP + 鉴权 + 重试
│           ├── errors.py          # 错误码释义
│           ├── render.py          # JSON / Markdown 输出
│           └── services/          # kr 拓词 / account 账户 / transfer 跨账户复制
├── avatars/expert.png
└── README.md
```

## 快速开始

```bash
cd skills/baidu-marketing-api

# 有没有已授权账户
python3 scripts/bmctl.py accounts list

# 拓词
python3 scripts/bmctl.py kr expand --seed "月季" --limit 20 --format md

# 多账户时指定账户
python3 scripts/bmctl.py --account axd kr expand --seed "猫粮"
```

一个 alias = 一个推广账户 = 一份独立凭据，存在 `~/.workbuddy/baidu-marketing/accounts/`。
接入新账户、多应用、跨账户复制的完整说明见
[references/auth.md](skills/baidu-marketing-api/references/auth.md)。

## 安装与首次使用

把专家包放到专家目录：

```
~/.workbuddy/plugins/marketplaces/my-experts/plugins/mybmo-baidu-ecommerce-marketing/
```

然后注册：

```bash
python3 <expert-manager>/scripts/register_expert.py <expert-dir>
```

**凭据不随专家包走**（令牌是个人资产，不打包），每台新电脑要单独授权一次。
完整流程见
[references/onboarding.md](skills/baidu-marketing-api/references/onboarding.md)，
覆盖环境检查、创建应用、拿 authCode、接入验证、权限域对照、故障排查。

## 头像

已生成在 `avatars/`。如需替换：PNG（推荐）或 JPG，512×512，≤500KB。

## 打包分享

```bash
python3 <expert-manager>/scripts/package_expert.py <expert-dir> <output-dir>
```
