# 鉴权与多账户管理

## 一、账户模型

**一个 alias = 一个推广账户 = 一份独立凭据。** 账户之间令牌互不共享，
所以跨账户操作必须先切换凭据，不能沿用上一个账户的 token。

```
~/.baidu-marketing/
├── accounts/
│   ├── wds02.json       # alias=wds02 的完整凭据（Unix 权限 600）
│   └── axd.json
└── default              # 纯文本，记录默认 alias
```

单账户内的字段来源优先级（高 → 低）：

| 优先级 | 来源 | 说明 |
|---|---|---|
| 1 | 环境变量 | `BAIDU_ACCESS_TOKEN`、`BAIDU_APP_ID`、`BAIDU_SECRET_KEY`、`BAIDU_USER_NAME`、`BAIDU_USER_ID`、`BAIDU_REFRESH_TOKEN` |
| 2 | `accounts/<alias>.json` | 账户本体，原子写入 |

账户选择优先级：`--account` 参数 > 环境变量 `BM_ACCOUNT` > `default` 文件。

相关环境变量：

| 变量 | 作用 |
|---|---|
| `BM_HOME` | 覆盖凭据根目录 |
| `BM_ACCOUNT` | 指定默认账户 alias |

## 二、调用时鉴权放在哪（最容易错的一项）

百度要求鉴权信息放在**请求体 JSON 的 header 字段**里，不是 HTTP 头：

```json
{
  "header": {
    "userName": "<账户中文名，如 baidu-XX电商-XX店>",
    "accessToken": "<OAuth accessToken>",
    "action": "API-PY-SDK"
  },
  "body": { "query": "<种子词>" }
}
```

三个字段的坑：

1. **`userName` 大小写**：必须是大写 N。写成 `username` 报 81012。
2. **`userName` 的值**：必须是**账户中文名**，不是数字 userId，也不是登录名。
   取法：`bmctl.py auth whoami` 返回的 `masterName`。
3. **`accessToken` 不能放 `token` 字段**：那是旧的加密通道，会报 84261。
4. `action` 只是标识字符串，写 `API-PY-SDK` 不代表真的加载了 SDK。

放到 HTTP 头里会稳定报 `8002 The Json message you provided is invalid`，`position=_sys`。

## 三、令牌生命周期

| 令牌 | 有效期 | 用途 |
|---|---|---|
| accessToken | 24 小时（86400s） | 每次业务调用携带 |
| refreshToken | 30 天（2592000s） | 换取新的 accessToken |

脚本行为：

- 每次调用前自动检查，过期前 5 分钟即视为过期并自动刷新
- 刷新成功后**同时更新 refreshToken**（百度会轮换），所以必须持久化，否则下一次刷新会失败
- 刷新结果写回凭据文件；`auth refresh --no-save` 可只刷新不落盘

refreshToken 过期后只能重新走完整授权流程，没有别的办法。

## 四、接入账户

一次接入只做一件事：**拿到 authCode → 换成令牌 → 存成 `accounts/<alias>.json`**。
三种接法结果完全一样，区别只在「authCode 怎么到手」。

| 接法 | 命令 | 适合 |
|---|---|---|
| 起服务自动接 | `auth serve` | 多账户、要给别人授权 |
| 手工复制授权码 | `auth exchange --code` | 一两个账户，偶尔接 |
| 直接写凭据文件 | 手工编辑 json | 已有 token，跳过换取 |

### 4.1 准备（百度侧，每个应用一次）

`https://dev2.baidu.com` → 应用管理 → 创建应用，拿到 `AppID`、`SecretKey`、
**开发者 uid**（创建应用的账号 uid，不等于推广账户的 userId）。

同时把**回调地址**填成公网可达的 URL。百度回调是服务端到服务端，`localhost` 无效。

### 4.2 起服务（推荐多账户）

```bash
uv run scripts/bmctl.py auth serve --port 8080 \
  --app-id <AppID> --developer-uid <开发者uid> --secret-key <SecretKey> --wait 900
```

服务启动后为每个账户生成独立链接，分头发出去：

```bash
uv run scripts/bmctl.py auth link --app-id <AppID> --developer-uid <开发者uid> \
  --callback https://<公网地址>/oauth/callback --alias acc_a
```

别名编进 `state`（`{base}.{alias}`），服务用 base 校验来源、用 alias 决定存到哪个账户。
所以不需要为每个账户开不同端口，也不用反复重启。

`--max N` 接满即退；`--once` 等价 `--max 1`；不传 `--user-name` 时自动调 `getUserInfo` 取账户中文名。

**安全边界**：默认只监听 `127.0.0.1`（公网靠隧道；容器场景可 `--host 0.0.0.0`，会告警），强制校验 state 的 base 部分，**不验签**
（AES 需额外引入第三方库，为可选校验不值）。风险可控：换令牌还要服务端持有的 secretKey，
且 authCode 一次性，伪造回调换不出令牌。

隧道或反代跑在**容器 / 另一台机器**时，默认的 `127.0.0.1` 收不到转发，需加 `--host 0.0.0.0`。
回调路径默认 `/oauth/callback`，两个应用若必须用不同路径，用 `--path` 区分。

### 4.3 手工换令牌

已经有 authCode 时（比如从 webhook 页面上复制的）：

```bash
uv run scripts/bmctl.py auth exchange --code <authCode> \
  --app-id <AppID> --secret-key <SecretKey> \
  --user-id <userId> --user-name "<账户中文名>" --alias acc_a
```

`grantType` 必须是 `auth_code`——官方 Java Demo 写成 `access_token` 是笔误。
`authCode` 一次性，用过即失效。

### 4.4 直接写凭据文件

手上已有令牌时，直接构造 `accounts/<alias>.json`（macOS/Linux 下记得 `chmod 600`；Windows 无 POSIX 权限位，靠用户目录 ACL）：

```json
{
  "alias": "acc_a",
  "user_name": "<账户中文名>",
  "app_id": "<AppID>",
  "secret_key": "<SecretKey>",
  "user_id": 88457159,
  "open_id": "<openId>",
  "access_token": "<accessToken>",
  "refresh_token": "<refreshToken>",
  "expires_at": 0,
  "refresh_expires_at": 0,
  "scope": {"75": "工具_其他工具"}
}
```

`expires_at` / `refresh_expires_at` 是 **Unix 时间戳（秒）**，不是日期字符串；
不确定就写 0（视为未过期），首次调用会按接口返回更新。缺 `refresh_token` 时这套 24 小时后失效。

### 4.5 多应用

账户分属不同 AppID / 开发者uid / SecretKey 时，用清单一次加载，不要起多个服务：

```json
// ~/.baidu-marketing/apps.json   Unix 权限 600（含密钥）
{
  "apps": [
    {"label": "主应用", "app_id": "<AppID-A>", "developer_uid": "<uid-A>", "secret_key": "<Key-A>"},
    {"label": "宠物店", "app_id": "<AppID-B>", "developer_uid": "<uid-B>", "secret_key": "<Key-B>"}
  ]
}
```

```bash
uv run scripts/bmctl.py auth serve --apps-file ~/.baidu-marketing/apps.json --wait 900
```

每个应用有自己的 base（`md5(appId_开发者uid)`），服务按回调 state 的前缀定位应用，
再用该应用的 SecretKey 换令牌，不会串密钥。

两条约束：

1. **alias 全局唯一**。跨应用同名会覆盖（程序打警告），建议加前缀 `main_rose`、`pet_rose`。
2. **清单只在接收授权时需要**。凭据里已带 app_id + secret_key，刷新令牌不依赖它。

### 4.6 state 回传（尚未实证）

多账户路由假设百度原样回传自定义 state。这是 OAuth 通用行为（巨量引擎等平台文档明确写
"回调时原样返回"），但百度营销平台本身没实测过——之前传的 state 就是
`md5(appId_开发者uid)`，回调回来也是它，两种假设都成立、无法区分。

服务做了兜底，`alias_source` 字段标明实际走哪条路：

| alias_source | 含义 |
|---|---|
| `state` | 别名生效，账户名完全可控 |
| `user_id` | state 被覆盖，退化为 `acct_<userId>` |
| `fallback` | 连 userId 都没有，用了 `--alias` 或 `default` |

首次真实授权建议特意验一次：用 `state=<base>.testacct` 生成链接，看回调后的 `alias_source`。
这一步决定多账户命名策略。

### 4.7 验证

```bash
uv run scripts/bmctl.py --account acc_a auth status
uv run scripts/bmctl.py --account acc_a kr expand --seed "测试" --limit 1
```

两条都通过才算接入完成。只跑第一条不够——凭据写对不等于权限够。

## 五、多账户常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `81020 The username information in the request is incorrect` | token 属于 A 账户，userName 填了 B 账户 | 用 `--account` 指定账户，不要手工拼凭据 |
| 刚才还能用，切账户后 89406 | 目标账户没开通该接口的权限域 | 权限是**按应用 + 账户**生效的，逐个确认 |
| `refresh_expired: true` | 30 天没用了 | 重新授权，没有别的办法 |
| 新增账户后第一次调用就失败 | authCode 已被用过（一次性），或 user_name 与令牌不匹配 | 重新走授权；核对 user_name 是否是该账户自己的中文名 |

给账户起 alias 时用小写字母/数字/下划线（如 `wds02`、`axd_pet`）。
alias 会直接做文件名，中文和特殊字符会导致路径问题。

账户中文名通过 `--user-name` 传入；不传时 `auth serve` 会用令牌自动调 `getUserInfo` 取。

## 六、权限范围怎么看

`auth status` 返回的 `scope` 是已开通权限：

```json
{ "75": "工具_其他工具" }
```

只有「工具」域时，关键词规划师可用，账户/投放/报告类接口返回 89406。
补权限需要在应用管理里申请对应能力域，然后**重新授权**（旧令牌不会自动获得新权限）。
