---
name: feishu-api
description: 通过飞书开放平台 API 查询和操作用户公司飞书数据（通讯录用户、部门、群聊、消息等），自动使用技能内置的 App ID/Secret 获取访问令牌。当用户要求查询、对接、同步或操作其公司飞书信息时使用；不适用于与飞书 API 无关的普通飞书话题。
---

# 飞书开放平台对接（feishu-api）

用公司自建应用的凭据访问[飞书开放平台](https://open.feishu.cn)，读取/操作飞书数据。

## 凭据

- 位置：`config.json`（与 `SKILL.md` 同目录），包含 `app_id`、`app_secret`、`base_url`。
- 首次使用：把同目录 `config.example.json` 复制为 `config.json`，填入公司飞书自建应用的 `app_id` / `app_secret`（向管理员索取，勿走公开渠道传输）。
- `app_secret` 是敏感凭据：不要打印、不要写入日志或交付文件，也不要将 `config.json` 提交到 Git 或公开仓库。

## 使用方式

优先使用 `scripts/feishu_client.py`（仅 Python 标准库，无需安装依赖）。客户端会自动获取并缓存 `tenant_access_token`（约 2 小时有效，过期自动刷新），无需手动处理鉴权。

```bash
python feishu_client.py token                              # 获取访问令牌（测试连通性）
python feishu_client.py user --email a@company.com         # 按邮箱查用户
python feishu_client.py user --mobile 13800138000          # 按手机号查用户
python feishu_client.py user --employee-id E001            # 按工号查用户
python feishu_client.py departments                        # 列出顶层部门
python feishu_client.py departments --parent <id>          # 列出某部门下级
python feishu_client.py members --department-id <id>       # 列出部门成员
python feishu_client.py chat --chat-id oc_xxx              # 查询群信息
python feishu_client.py request --method GET --path /contact/v3/users/me   # 调用任意接口
```

- 也可以把 `feishu_client.py` 作为 Python 库导入使用（如 `get_user`、`list_departments`、`send_text_message`、`api_request`），或通过 `request` 子命令调用未预置的接口。
- 本机没有 `python` 命令时，让 Codex 查找当前环境可用的 Python 解释器路径（或询问用户）。

## 关键约束

- **权限前置**：应用必须在[飞书开发者后台](https://open.feishu.cn/app)开通对应 scope 并发布应用版本，否则接口返回 `code=99991668`（permission denied）。具体接口所需权限见 `references/api-guide.md`（用到具体接口时再读取）。
- **写操作需确认**：`send`（发消息）等变更操作会真实影响公司数据，执行前先向用户确认收件人与内容。
- **错误处理**：接口返回 `code != 0` 即为失败；客户端会在令牌失效（`99991663`）时自动刷新重试一次，其余错误把 `code`/`msg` 反馈给用户。