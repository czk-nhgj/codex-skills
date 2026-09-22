# codex-skills（团队 Codex 技能）

本仓库用于团队共享 Codex 技能。

## 技能列表

### feishu-api

飞书开放平台对接技能，支持通讯录、部门、群聊、多维表格和电子表格查询与操作。

### amazon-replenishment-ops

亚马逊运营端备货参数设置技能。运营指定站点、目标亚马逊月均货值和目标售出率后，Codex 会自动完成：

- 预估并设置 `AI亚马逊月均`
- 计算站点上限货值范围
- 设置 `AI下限` 和 `AI销量偏离度`
- 回读飞书并校验货值和 `是否计算` 规则

该技能依赖 `feishu-api`，两个技能需要同时安装。

## 安装

让 Codex 使用 `$skill-installer`，从本仓库安装所需技能：

```text
请使用 $skill-installer 安装 GitHub 仓库 czk-nhgj/codex-skills 中的：
1. skills/feishu-api
2. skills/amazon-replenishment-ops
```

也可以手动把 `skills` 下的技能文件夹复制到 `C:\Users\<用户名>\.codex\skills\`，然后重启 Codex。

## 飞书凭据

仓库不包含明文密钥。`skills/feishu-api/config.json.enc` 是加密后的团队飞书凭据。

首次使用 `feishu-api` 或 `amazon-replenishment-ops` 前，在 `skills/feishu-api` 目录执行：

```bash
python unlock.py
```

按提示输入团队共享密码，成功后会在本机生成 `config.json`。该文件已被 `.gitignore` 忽略，不会提交。

团队密码请通过公司安全渠道向技能管理员获取。

## 测试

在 `skills/feishu-api` 目录执行：

```bash
python scripts/feishu_client.py token
```

看到成功返回的 token 信息后，技能即可使用。
