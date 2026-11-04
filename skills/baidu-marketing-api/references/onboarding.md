# 全新电脑上首次使用

这份文档面向"刚装好技能、什么都还没配"的场景。目标是让你在 10 分钟内跑通第一次真实取数。

## 零、先确认你处在哪一步

在技能的 `scripts/` 目录下执行（技能加载时会给出 base directory）：

```bash
uv run scripts/bmctl.py accounts list
```

| 结果 | 含义 | 下一步 |
|---|---|---|
| 显示 1 个或多个账户，`usable: true` | 已经可用 | 跳到「五、开始使用」 |
| `总数 0` / 提示"还没有任何已授权账户" | 没有凭据 | 继续往下走 |
| 报 `No such file` / `uv: command not found` | 环境问题 | 看「一、环境检查」 |

排查顺序永远是：**环境 → 账户 → 权限**，不要跳步。

## 一、环境检查

只要装一个东西：**uv**。Python 由它负责，依赖由它装，你不需要 `pip install` 任何包。

```bash
uv --version
```

没有的话按平台装（官方脚本，一次性）：

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows（PowerShell）
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

装完重新开一个终端，`uv --version` 有输出就行。

然后所有命令都用 `uv run` 开头：

```bash
uv run scripts/bmctl.py accounts list
```

几个要点：

- **三平台同一条命令**，不用再区分 `python3` 和 `py -3`
- **首次运行会慢几秒**，那是 uv 在建隔离环境（缓存在 `uv cache dir`，之后复用），不是卡死
- uv 的进度提示走 **stderr**，脚本输出的 JSON 走 **stdout**，两者分开看
- 降级：uv 实在装不上、但机器已有 Python 3.9+ 时，可以用 `python3 <路径>/scripts/bmctl.py`
  跑同样的命令；此时版本过低会**以退出码 6 结束**并给出中文提示

Windows 上如果输出中文变成乱码，现在的脚本会把标准输出统一设成 UTF-8；
若终端仍显示乱码，执行一次：

```bash
chcp 65001
```

或设置环境变量 `PYTHONIOENCODING=utf-8`。这只是显示问题，不影响取数。

## 二、安装技能

技能就是一个目录。放进你的 agent 加载技能的位置即可，**不绑定任何特定平台**：

```bash
# 通用做法：整目录拷进 agent 的 skills 目录
# 目录名保持 baidu-marketing-api，且 SKILL.md 要在该目录根部
cp -r baidu-marketing-api <你的 agent 的 skills 目录>/
```

| 宿主 | 用户级 | 项目级 |
|---|---|---|
| WorkBuddy / CodeBuddy | `~/.codebuddy/skills/` | `<项目>/.codebuddy/skills/` |
| 其它按 SKILL.md 约定的 agent | 见其文档 | 见其文档 |

判断标准只有一条：**agent 能扫到 `SKILL.md`**。

> 如果你装的是**完整专家包**（含 MyBMO 人设），技能已经打包在里面，跳过这一步。

> **凭据不会随技能或专家包一起走。** 这是有意的安全设计——令牌是个人资产，
> 不该打包分享。所以每台新电脑都要单独授权一次。

## 三、准备授权（需要在百度侧操作）

这是整个流程里最麻烦的一步，因为涉及百度开发者后台。分三小步：

### 3.1 创建应用

打开 `https://dev2.baidu.com` → 应用管理 → 创建应用，记下三个值：

| 值 | 说明 |
|---|---|
| `AppID` | 应用唯一标识 |
| `SecretKey` | 应用密钥，换令牌时用 |
| 开发者 uid | **创建应用的账号 uid**，不是推广账户的 userId，两者不同 |

同时在应用管理里填写**回调地址**（下一小节会用到），并为应用申请需要的权限域
（至少勾「工具」，要投放管理再加「投放管理」）。

### 3.2 拿 authCode（用内置回调服务）

百度在同意授权后，以 **GET 方式、服务端到服务端**回调你填的地址，带回一次性 `authCode`。
浏览器不参与这次回调，所以 `localhost` 无效，必须公网可达。

技能**内置了回调服务**，不用自己写。四步：

**① 起隧道**（另开一个终端，把公网地址转到本机 8080）

```bash
cloudflared tunnel --url http://127.0.0.1:8080
# 或 frp / ngrok，拿到形如 https://xxx.trycloudflare.com 的地址
```

**② 填回调地址**

到 `dev2.baidu.com` 应用管理，把 `https://xxx.trycloudflare.com/oauth/callback`
填成回调地址（不能带 `?` 或 `%`）。

**③ 起本地服务**

```bash
uv run scripts/bmctl.py auth serve --port 8080 \
  --app-id <AppID> \
  --developer-uid <开发者uid> \
  --callback https://xxx.trycloudflare.com/oauth/callback \
  --scope <权限代码> \
  --wait 900
```

服务启动后会打印一条授权链接。`state` 不传时按 `md5(appId_开发者uid)` 自动推导。

**④ 打开授权链接并同意**

授权完成瞬间，百度回调打通本地服务，服务接住 `authCode` 并自动退出，输出 JSON。

如果第 ③ 步同时给了 `--secret-key` `--user-id` `--user-name` `--alias`，
**会直接换令牌并落盘**，一步到位；没给的话，把输出的 `auth_code` 拿去执行 3.3。

> 服务只监听本机、靠隧道暴露公网，安全设计与取舍见 `references/auth.md` 4.2 节。

**接多个账户或分属不同应用时**，不用反复重启服务：用 `auth link --alias 账户A` 为每个账户
生成独立链接，`--apps-file` 一次加载多个应用，具体见 `references/auth.md` 4.5 节。

只想生成链接、不启动服务时：

```bash
uv run scripts/bmctl.py auth link --app-id <AppID> --developer-uid <开发者uid> \
  --callback https://xxx.trycloudflare.com/oauth/callback --scope <权限码>
```

### 3.3 换成令牌并落地

> 如果 3.2 的 `auth serve` 已经返回了 `credential` 字段，说明已自动换好，跳过本步。

```bash
uv run scripts/bmctl.py auth exchange \
  --code <authCode> \
  --app-id <AppID> \
  --secret-key <SecretKey> \
  --user-id <该账户 userId> \
  --user-name "<该账户中文名>" \
  --alias <别名>
```

`--alias` 是以后 `--account` 用的名字，用小写字母/数字/下划线（如 `wds02`、`axd_pet`）。
`--user-name` 填账户中文名（如 `baidu-XX电商-XX店`），**不是 userId，也不是登录名**。

成功后凭据落在 `~/.baidu-marketing/accounts/<alias>.json`（macOS/Linux 权限 600；Windows 无 POSIX 权限位，靠用户目录 ACL，默认仅本人可读）。

## 四、验证

```bash
# 1. 账户状态
uv run scripts/bmctl.py --account <别名> auth status

# 2. 真实取数
uv run scripts/bmctl.py --account <别名> kr expand --seed "测试词" --limit 3 --format md
```

第 2 条能返回关键词、搜索量、出价，就算彻底跑通了。

如果第 1 条 `usable: true` 但第 2 条报 `89406`，那不是令牌问题，是**权限域没开通**，
见下一节。

## 五、开始使用

通了之后，直接用自然语言提需求，agent 会自己调脚本：

- 「帮我给 XX 产品拓词，按搜索量和推荐出价分组」
- 「这两个词哪个更值得投」
- 「把账户 A 的这个计划在账户 B 投一遍」

唯一要记住的约定：**多账户时必须说清是哪个账户**，否则专家会问，别嫌烦——
账户张冠李戴会把 A 的数据说成 B 的。

## 六、权限域对照

能力不是全开的，取决于应用申请了哪些权限域：

| 能力 | 所需权限域 | 未开通时 |
|---|---|---|
| 关键词拓词、搜索量、推荐出价 | 工具 | — |
| 账户信息、余额、付款记录 | 账户管理 | `89406` |
| 计划/单元/关键词/创意 读写 | 投放管理 | `89406` |
| 报告中心、数据下载 | 报告 | `89406` |

补开权限后**必须重新走一次授权**，旧令牌不会自动获得新权限。

## 七、故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| `python3: command not found` | 没装 Python 或没进 PATH | 装 Python 3.9+ |
| 中文输出乱码 | Windows 控制台 GBK | `chcp 65001` |
| `还没有任何已授权账户` | 还没接入 | 走第三节 |
| `81020 The username information...` | `--user-name` 不是该账户的中文名 | 改为该账户自己的中文名 |
| `81012 Username is not set` | 账户名为空 | 补 `--user-name` |
| `89406 The access token ... invalidate` | 权限域未开通（不是令牌失效） | 去开发者后台补权限并重新授权 |
| `refresh_expired: true` | 30 天没用 | 重新走授权，没有别的办法 |
| `authCode` 用不了第二次 | 它是一次性凭据 | 重新走授权拿新的 |
| `端口 8080 无法监听` | 端口被占用 | 换 `--port 8081`，或关掉占用进程 |
| `auth serve` 一直等到超时 | 隧道没指向本机、回调地址没填对、或授权没完成 | 先用 `curl https://<隧道域名>/healthz` 确认隧道通 |
| `state 不匹配` | 授权链接不是这次 `serve` 生成的 | 用 `serve` 打印的那条链接，别复用旧的 |
| 授权页打开报参数错误 | 缺 `scope` 或 `state` 格式不对 | 核对授权链接五个参数 |

## 八、想彻底重置

```bash
# 删掉某个账户
uv run scripts/bmctl.py accounts remove <别名>

# 全部清空（谨慎，删的是凭据不是数据）
rm -rf ~/.baidu-marketing
```

清空后等同于全新电脑，按第二节重新开始。
