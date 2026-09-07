# feishu-api 技能分享包

飞书开放平台对接技能：查询公司飞书数据（通讯录用户/部门/多维表格/群聊），可发消息。
配套 `scripts/feishu_client.py` 客户端，仅用 Python 标准库，无需安装依赖。

## 安装（同事电脑）

方式 A（手动）：把本仓库里的 `skills\feishu-api` 文件夹复制到 `C:\Users\<你的用户名>\.codex\skills\` 下，重启 Codex 即可使用。

方式 B（团队 Git 仓库，推荐）：把 `feishu-api` 文件夹放进仓库的 `.agents/skills/` 目录并提交，同事克隆仓库后 Codex 会自动发现该技能（项目级技能随仓库共享）。

方式 C（从 GitHub 安装）：把 `feishu-api` 提交到 Git 仓库后，同事在 Codex 里让 `$skill-installer` 从仓库路径安装。

## 首次使用前：配置凭据

1. 进入 `feishu-api` 目录，把 `config.example.json` 复制为 `config.json`。
2. 填入公司飞书自建应用的 `app_id` / `app_secret`（找飞书管理员索取，通过公司安全渠道传输，不要发在群里/邮件明文）。

## 注意

- 本分享包**不含真实密钥**（已脱敏）。请勿把填好密钥的 `config.json` 提交到 Git。
- 应用需在飞书开发者后台开通对应权限（通讯录 / 多维表格 / 消息）并发布版本，否则接口返回权限错误。
- 测试连通性：`python feishu_client.py token`。
