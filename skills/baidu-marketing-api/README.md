# baidu-marketing-api

WorkBuddy 技能：百度营销开放平台的取数与投放能力（多账户、关键词规划师拓词、账户数据、
跨账户复制、写操作审批）。由真实 API 返回，不含任何估算数字。

## 安装

技能目录名必须是 `baidu-marketing-api`（`SKILL.md` 的 `name` 字段与之一致）。

**用户级**（所有项目可用）：

```bash
mkdir -p ~/.codebuddy/skills
cp -r baidu-marketing-api ~/.codebuddy/skills/
```

**项目级**（只在本项目可用）：

```bash
mkdir -p .codebuddy/skills
cp -r baidu-marketing-api .codebuddy/skills/
```

装好后在 WorkBuddy 里发起一个需要百度营销数据的任务，技能会自动被选中；
也可以在对话里直接说"用 baidu-marketing-api 查一下账户余额"。

## 依赖

只依赖 **uv** 一个可执行文件，Python 解释器与第三方库由它托管：

```bash
uv --version
```

没有的话装一个（macOS / Linux）：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows（PowerShell）：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

运行时依赖声明在 `scripts/bmctl.py` 头部的 PEP 723 内联块里，uv 据此自动准备隔离环境，
**不需要 `pip install`**。首次运行会下载依赖并缓存，之后复用。

## 验证安装

```bash
cd baidu-marketing-api
uv run scripts/bmctl.py accounts list
```

- 返回 `{"total": 0, "accounts": []}` → 安装成功，只是还没接入账户
- 提示 `uv: command not found` → 先装 uv
- 提示 `No such file` → 目录名或当前路径不对，确认在 `baidu-marketing-api/` 内执行

接入百度账户（创建应用、拿 authCode、换令牌）的完整流程见
[`references/onboarding.md`](references/onboarding.md)。

## 目录结构

```
baidu-marketing-api/
├── SKILL.md                  # 技能入口：自检、命令清单、字段含义、能力边界
├── runtime.json              # 运行方式、uv 安装命令、凭据目录
├── references/
│   ├── onboarding.md         # 全新电脑上首次接入（给人看）
│   ├── auth.md               # 鉴权技术细节与多账户
│   ├── auth-sop.md           # 鉴权交互 SOP（Agent 用）
│   ├── keyword-sop.md        # 图片转投流关键词 SOP（Agent 用）
│   ├── write-rules.md        # 写操作行为规范（唯一真源）
│   └── api-index.md          # 129 个服务 / 389 个接口索引
└── scripts/
    ├── bmctl.py              # CLI 入口（参数解析 + 输出渲染）
    └── bmclient/             # 核心库：鉴权、传输、服务封装、审批
```

## 凭据放在哪

`~/.workbuddy/baidu-marketing/accounts/<alias>.json`，**不随技能分发**，每台机器需单独授权一次。
可用环境变量 `BM_HOME` 改到别处。

## 安全边界

- 写操作强制两步：预览拿 digest → 用户确认 → 执行，详见
  [`references/write-rules.md`](references/write-rules.md)
- 每次真实写入追加审计到 `~/.workbuddy/baidu-marketing/audit/YYYY-MM-DD.jsonl`
- 授权回调服务默认只监听 `127.0.0.1`，公网靠隧道转发
