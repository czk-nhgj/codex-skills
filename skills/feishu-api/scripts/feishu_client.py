#!/usr/bin/env python3
"""飞书开放平台客户端（feishu-api skill）。

仅使用 Python 标准库，无需安装第三方依赖。
凭据从技能根目录的 config.json 读取（app_id / app_secret / base_url）。

用法示例：
    python feishu_client.py token
    python feishu_client.py user --email alice@company.com
    python feishu_client.py user --mobile 13800138000
    python feishu_client.py user --employee-id E001
    python feishu_client.py departments [--parent <id>] [--department-id-type open_id]
    python feishu_client.py members --department-id <id>
    python feishu_client.py chat --chat-id oc_xxxxxxxx
    python feishu_client.py send --receive-id <id> --receive-id-type user_id --text "你好"
    python feishu_client.py request --method GET --path /contact/v3/users/me

也可作为 Python 库导入使用：from feishu_client import get_user, list_departments, api_request, ...
"""

import argparse
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "https://open.feishu.cn/open-apis"
TOKEN_ENDPOINT = "/auth/v3/tenant_access_token/internal"
TOKEN_CACHE_FILE = os.path.join(tempfile.gettempdir(), "feishu_api_token_cache.json")
TOKEN_EXPIRE_BUFFER = 120  # 提前 120 秒刷新，避免边界过期
DEFAULT_TIMEOUT = 20
INVALID_TOKEN_CODE = 99991663


class FeishuError(Exception):
    """飞书接口或网络调用失败。"""


def load_config(config_path=None):
    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent / "config.json"
    else:
        config_path = Path(config_path)
    if not Path(config_path).exists():
        raise FeishuError(f"配置文件不存在: {config_path}")
    with open(config_path, encoding="utf-8") as f:
        data = json.load(f)
    missing = [k for k in ("app_id", "app_secret") if not data.get(k)]
    if missing:
        raise FeishuError(f"config.json 缺少字段: {', '.join(missing)}")
    data.setdefault("base_url", DEFAULT_BASE_URL.rstrip("/"))
    return data


def http_request(method, url, headers=None, body=None, timeout=DEFAULT_TIMEOUT):
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = dict(headers or {})
        headers.setdefault("Content-Type", "application/json; charset=utf-8")
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        if not raw:
            raise FeishuError(f"HTTP {exc.code}: {url}")
    except urllib.error.URLError as exc:
        raise FeishuError(f"网络请求失败: {exc.reason} ({url})")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise FeishuError(f"响应不是合法 JSON: {raw[:200]}")


def _read_token_cache():
    try:
        with open(TOKEN_CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _write_token_cache(cache):
    try:
        tmp = TOKEN_CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cache, f)
        os.replace(tmp, TOKEN_CACHE_FILE)
    except OSError:
        pass  # 缓存失败不影响功能，只是每次重新获取


def get_tenant_access_token(config, force=False):
    """获取并缓存 tenant_access_token（默认有效期 7200 秒）。"""
    now = time.time()
    if not force:
        cached = _read_token_cache().get(config["app_id"])
        if cached and cached.get("expire_at", 0) > now:
            return cached["tenant_access_token"]
    resp = http_request(
        "POST",
        config["base_url"] + TOKEN_ENDPOINT,
        body={"app_id": config["app_id"], "app_secret": config["app_secret"]},
    )
    if resp.get("code") != 0:
        raise FeishuError(
            f"获取 tenant_access_token 失败: code={resp.get('code')} msg={resp.get('msg')}"
        )
    token = resp["tenant_access_token"]
    expire_in = int(resp.get("expire", 7200))
    cache = _read_token_cache()
    cache[config["app_id"]] = {
        "tenant_access_token": token,
        "expire_at": now + expire_in - TOKEN_EXPIRE_BUFFER,
    }
    _write_token_cache(cache)
    return token


def api_request(config, method, path, params=None, body=None, retry=True, timeout=DEFAULT_TIMEOUT):
    """调用业务接口，自动携带令牌；令牌失效时刷新并重试一次。"""
    path = path if path.startswith("/") else "/" + path
    url = config["base_url"] + path
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    token = get_tenant_access_token(config)
    headers = {"Authorization": "Bearer " + token}
    resp = http_request(method, url, headers=headers, body=body, timeout=timeout)
    if resp.get("code") == 0:
        return resp.get("data") or {}
    if resp.get("code") == INVALID_TOKEN_CODE and retry:
        get_tenant_access_token(config, force=True)
        return api_request(config, method, path, params=params, body=body, retry=False, timeout=timeout)
    raise FeishuError(
        f"接口调用失败: {method} {path} code={resp.get('code')} msg={resp.get('msg')}"
    )


def collect_paginated(config, path, params=None, item_key="items", page_size=50):
    """自动翻页收集列表接口的全部数据。"""
    params = dict(params or {})
    params.setdefault("page_size", page_size)
    items = []
    while True:
        data = api_request(config, "GET", path, params=params)
        items.extend(data.get(item_key, []))
        if data.get("has_more"):
            params["page_token"] = data.get("page_token")
        else:
            break
    return items


# ---------- 便捷函数（可 import 使用） ----------

def get_user(config, user_id, user_id_type="open_id"):
    """按 open_id/union_id/user_id/email/mobile 查询用户。"""
    data = api_request(
        config, "GET", f"/contact/v3/users/{user_id}", params={"user_id_type": user_id_type}
    )
    return data.get("user", data)


def list_departments(config, parent_department_id=None, fetch_child=False,
                     department_id_type="open_id", page_size=50):
    params = {"department_id_type": department_id_type}
    if parent_department_id is not None:
        params["parent_department_id"] = parent_department_id
    if fetch_child:
        params["fetch_child"] = "true"
    return collect_paginated(config, "/contact/v3/departments", params=params, page_size=page_size)


def list_department_members(config, department_id, department_id_type="open_id", page_size=50):
    params = {"department_id_type": department_id_type}
    return collect_paginated(
        config, f"/contact/v3/departments/{department_id}/members", params=params, page_size=page_size
    )


def get_chat(config, chat_id):
    return api_request(config, "GET", f"/im/v1/chats/{chat_id}")


def send_text_message(config, receive_id, receive_id_type, text):
    """发送文本消息。receive_id_type: open_id/user_id/union_id/email/chat_id。"""
    body = {
        "receive_id": receive_id,
        "msg_type": "text",
        "content": json.dumps({"text": text}, ensure_ascii=False),
    }
    return api_request(
        config, "POST", "/im/v1/messages",
        params={"receive_id_type": receive_id_type}, body=body,
    )


# ---------- CLI ----------

def _print(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_token(config, args):
    token = get_tenant_access_token(config, force=args.force)
    _print({"app_id": config["app_id"], "tenant_access_token": token})


def cmd_user(config, args):
    if args.user_id:
        user_id, id_type = args.user_id, "open_id"
    elif args.email:
        user_id, id_type = args.email, "email"
    elif args.mobile:
        user_id, id_type = args.mobile, "mobile"
    elif args.employee_id:
        user_id, id_type = args.employee_id, "employee_id"
    else:
        raise SystemExit("请提供 --user-id / --email / --mobile / --employee-id 之一")
    _print(get_user(config, user_id, id_type))


def cmd_departments(config, args):
    _print(list_departments(
        config,
        parent_department_id=args.parent,
        fetch_child=args.fetch_child,
        department_id_type=args.department_id_type,
    ))


def cmd_members(config, args):
    _print(list_department_members(
        config, args.department_id, department_id_type=args.department_id_type
    ))


def cmd_chat(config, args):
    _print(get_chat(config, args.chat_id))


def cmd_send(config, args):
    _print(send_text_message(config, args.receive_id, args.receive_id_type, args.text))


def cmd_request(config, args):
    params = {}
    for kv in args.query or []:
        key, sep, value = kv.partition("=")
        if not sep:
            raise SystemExit(f"查询参数格式应为 key=value: {kv}")
        params[key] = value
    body = json.loads(args.body) if args.body else None
    _print(api_request(config, args.method, args.path, params=params, body=body))


def build_parser():
    parser = argparse.ArgumentParser(
        prog="feishu_client.py", description="飞书开放平台客户端（feishu-api skill）"
    )
    parser.add_argument("--config", help="config.json 路径（默认技能目录下）")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("token", help="获取 tenant_access_token")
    p.add_argument("--force", action="store_true", help="忽略缓存强制重新获取")

    p = sub.add_parser("user", help="查询用户（邮箱/手机号/工号/open_id）")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--user-id", help="open_id")
    g.add_argument("--email", help="邮箱")
    g.add_argument("--mobile", help="手机号")
    g.add_argument("--employee-id", help="工号")

    p = sub.add_parser("departments", help="列出部门")
    p.add_argument("--parent", help="父部门 ID（不填为顶层）")
    p.add_argument("--fetch-child", action="store_true", help="递归列出所有子部门")
    p.add_argument("--department-id-type", default="open_id",
                   choices=["open_id", "department_id", "chat_id"])

    p = sub.add_parser("members", help="列出部门成员")
    p.add_argument("--department-id", required=True)
    p.add_argument("--department-id-type", default="open_id",
                   choices=["open_id", "department_id", "chat_id"])

    p = sub.add_parser("chat", help="查询群信息")
    p.add_argument("--chat-id", required=True)

    p = sub.add_parser("send", help="发送文本消息（写操作，先与用户确认）")
    p.add_argument("--receive-id", required=True)
    p.add_argument("--receive-id-type", required=True,
                   choices=["open_id", "user_id", "union_id", "email", "chat_id"])
    p.add_argument("--text", required=True)

    p = sub.add_parser("request", help="调用任意开放平台接口")
    p.add_argument("--method", required=True, choices=["GET", "POST", "PUT", "PATCH", "DELETE"])
    p.add_argument("--path", required=True, help="接口路径，如 /contact/v3/users/me")
    p.add_argument("--query", action="append", help="查询参数 key=value（可重复）")
    p.add_argument("--body", help="请求体 JSON 字符串")

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        handlers = {
            "token": cmd_token,
            "user": cmd_user,
            "departments": cmd_departments,
            "members": cmd_members,
            "chat": cmd_chat,
            "send": cmd_send,
            "request": cmd_request,
        }
        handlers[args.command](config, args)
        return 0
    except FeishuError as exc:
        print(f"[feishu] 错误: {exc}", file=sys.stderr)
        return 1
    except SystemExit:
        raise
    except Exception as exc:  # 兜底，避免堆栈刷屏
        print(f"[feishu] 未预期错误: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())