# codex-skills（feishu-api 技能）

飞书开放平台对接技能：查询公司飞书数据（通讯录用户/部门/多维表格/群聊），可发消息。
配套 `scripts/feishu_client.py` 客户端，仅用 Python 标准库；解密工具 `unlock.py` 使用 `cryptography`（Codex 自带 Python 已包含）。

## 安装（同事电脑）

在 Codex 中让 `$skill-installer` 从本仓库路径 `skills/feishu-api` 安装；或手动把 `skills\feishu-api` 文件夹复制到 `C:\Users\<你的用户名>\.codex\skills\` 下并重启 Codex。

## 首次使用：解锁凭据（需要团队密码）

仓库**不包含明文密钥**。`skills/feishu-api/config.json.enc` 是团队飞书凭据的加密文件（AES-256-GCM + scrypt）。在技能目录执行：

    python unlock.py

按提示输入团队共享密码，成功后会生成本地 `config.json`（已被 `.gitignore` 忽略，不会提交），技能即可直接使用，无需其他配置。

团队密码不随仓库分发，请向技能管理员（GitHub: czk-nhgj）通过公司安全渠道索取，不要发在公开群或提交到仓库。

## 测试连通性

    python scripts/feishu_client.py token
