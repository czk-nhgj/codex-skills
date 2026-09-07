# 飞书开放平台 API 参考（feishu-api）

> 按需读取：查询/操作具体数据前查看对应接口的参数与所需权限。

## 基础信息

- Base URL：`https://open.feishu.cn/open-apis`（`config.json` 中可覆盖）。
- 鉴权：`POST /auth/v3/tenant_access_token/internal`，请求体 `{"app_id": "...", "app_secret": "..."}`，返回 `tenant_access_token`（有效期 7200 秒）。客户端 `feishu_client.py` 已自动获取并缓存。
- 业务接口请求头携带 `Authorization: Bearer <tenant_access_token>`。
- 统一响应：`{"code": 0, "msg": "success", "data": {...}}`；`code != 0` 即失败。

## 常用接口

| 用途 | 方法与路径 | 关键参数 | 所需 scope |
| --- | --- | --- | --- |
| 查询用户 | GET `/contact/v3/users/{user_id}` | `user_id_type` ∈ `open_id`/`union_id`/`user_id`/`email`/`mobile`；路径 `{user_id}` 填对应值 | `contact:user.base:readonly` |
| 当前用户 | GET `/contact/v3/users/me` | 无 | `contact:user.base:readonly` |
| 列出部门 | GET `/contact/v3/departments` | `parent_department_id`（默认根部门直属）、`fetch_child`、`department_id_type` | `contact:department.base:readonly` |
| 列出部门成员 | GET `/contact/v3/departments/{department_id}/members` | `department_id_type`、`page_size`、`page_token` | `contact:user.base:readonly` |
| 查询群信息 | GET `/im/v1/chats/{chat_id}` | 无 | `im:chat:readonly` |
| 发送文本消息 | POST `/im/v1/messages?receive_id_type={type}` | 请求体 `{"receive_id": "...", "msg_type": "text", "content": "{\"text\":\"...\"}"}`；`receive_id_type` ∈ `open_id`/`user_id`/`union_id`/`email`/`chat_id` | `im:message`、`im:message:send_as_bot` |

分页：列表接口返回 `has_more` 与 `page_token`；客户端 `collect_paginated()` 已自动翻页。

## 常见错误码

| code | 含义 | 处理 |
| --- | --- | --- |
| 99991663 | 令牌无效/过期 | 客户端自动刷新重试 |
| 99991668 | 无权限（缺少 scope） | 到开发者后台开通权限并发布版本 |
| 230001 | 查无此人 | 核对邮箱/手机号/工号 |
| 230002 | 部门不存在 | 核对部门 ID |

## 权限开通步骤

1. 打开[飞书开发者后台](https://open.feishu.cn/app)，进入本应用「权限管理」。
2. 按上表开通所需 scope，保存后「创建版本 → 申请发布」（企业管理员审批后生效；开发调试模式可先自测）。
3. 通讯录接口还需在「通讯录权限」中把应用加入对应部门/成员的可见范围；否则能取到令牌但读不到数据。
4. 若按邮箱/手机号查询时返回字段为空，需额外开通 `contact:user.email:readonly`、`contact:user.phone:readonly`。
5. 给用户发消息前，该用户需先与机器人（本应用）产生过会话，或把机器人拉入目标群。

## 文档

- 开放平台总览：https://open.feishu.cn/document/
- 通讯录：https://open.feishu.cn/document/server-docs/contact-v3/introduction
- 即时通讯（消息/群）：https://open.feishu.cn/document/server-docs/im-v1/introduction
- 鉴权：https://open.feishu.cn/document/server-docs/authentication-management/access-token/tenant_access_token_internal