"""把周报发到 QQ（走本机 roost 的 /api/qq/call）。

用法：
    python weekly_push.py            # 生成并发送
    python weekly_push.py --dry      # 只打印，不发送
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

import engine
import store

ROOST = "http://127.0.0.1:8080"
GROUPS = Path.home() / ".dsh" / "dsh-roost" / "roost" / "data" / "bots" / "main" / "groups.json"


def _post(path: str, payload: dict, timeout: float = 8.0):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(ROOST + path, data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def _get(path: str, timeout: float = 5.0):
    with urllib.request.urlopen(ROOST + path, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def group_openid() -> str:
    """从 roost 的 groups.json 里取第一个群的 openid（完整长度）。"""
    if not GROUPS.exists():
        return ""
    raw = json.loads(GROUPS.read_text(encoding="utf-8"))

    def _pick(it):
        if isinstance(it, dict):
            return it.get("groupOpenid") or it.get("group_openid") or it.get("openid") or ""
        return str(it) if isinstance(it, str) else ""

    # 两种常见形态：{openid: {...}} 或 {groups: [...]}
    pool = []
    if isinstance(raw, dict) and "groups" in raw and isinstance(raw["groups"], list):
        pool = raw["groups"]
    elif isinstance(raw, dict):
        pool = list(raw.values()) or list(raw.keys())
    elif isinstance(raw, list):
        pool = raw

    for it in pool:
        gid = _pick(it)
        if not gid and isinstance(it, str):
            gid = it
        if gid and len(gid) >= 20:
            return gid
    return ""


def push_qq(text: str) -> dict:
    """把文本发到 QQ 群；返回 roost 的响应。"""
    status = _get("/api/status")
    if not status.get("connected"):
        return {"ok": False, "error": "机器人不在线（roost state=%s）" % status.get("state")}
    gid = group_openid()
    if not gid:
        return {"ok": False, "error": "没找到群 openid，请先让机器人在群里说过话"}
    for chunk in _split(text, 900):
        _post("/api/qq/call", {"method": "sendGroup",
                               "args": {"__target": gid, "content": chunk, "msg_type": 0}})
        time.sleep(0.6)
    return {"ok": True, "group": gid, "chunks": len(_split(text, 900))}


def _split(text: str, size: int) -> list[str]:
    out, buf = [], ""
    for line in text.splitlines(True):
        if len(buf) + len(line) > size and buf:
            out.append(buf)
            buf = ""
        buf += line
    if buf:
        out.append(buf)
    return out


def build_report(days: int = 7) -> tuple[str, Path]:
    s = store.Store()
    text = engine.weekly_markdown(s.weekly_report(days))
    out_dir = Path(s.path).parent / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / ("周报_%s.md" % time.strftime("%Y%m%d"))
    out.write_text(text, encoding="utf-8")
    return text, out


def main() -> int:
    text, out = build_report(7)
    print("周报已生成：%s（%d 字）" % (out, len(text)))
    if "--dry" in sys.argv:
        print(text[:400])
        return 0
    try:
        res = push_qq(text)
    except Exception as exc:
        print("发送失败：", exc)
        return 1
    print("推送结果：", res)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
