#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快手作品保存台 · 本地解析引擎
仅使用 Python 标准库，不需要安装任何依赖。

启动：
    python server.py
然后打开：
    http://127.0.0.1:8787
"""

from __future__ import annotations

import json
import os
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VERSION = "1.0.0"
ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PORT = int(os.environ.get("KS_PORT", "8787"))

UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)
UA_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

PAGE_HOSTS = ("kuaishou.com", "chenzhongtech.com", "kwai.com", "gifshow.com")
MAX_PAGE_BYTES = 8 * 1024 * 1024

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
}

PROXY_HEADERS = {
    "User-Agent": UA_MOBILE,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
    "Referer": "https://www.kuaishou.com/",
}


class FetchError(Exception):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _check_page_url(url: str) -> None:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise FetchError("只支持 http / https 链接")
    host = (parts.hostname or "").lower()
    if not host:
        raise FetchError("链接缺少域名")
    if not any(host == suffix or host.endswith("." + suffix) for suffix in PAGE_HOSTS):
        raise FetchError("这不是快手域名下的链接")
    if re.fullmatch(r"[0-9.]+", host):
        raise FetchError("不支持直接访问 IP")


def fetch_page(url: str, referer: str | None = None) -> tuple[str, str, bytes]:
    """手动跟随跳转，逐跳校验域名，返回 (final_url, content_type, body)。"""
    headers = dict(PROXY_HEADERS)
    if referer:
        headers["Referer"] = referer

    current = url
    for _ in range(8):
        _check_page_url(current)
        req = urllib.request.Request(current, headers=headers, method="GET")
        try:
            resp = _OPENER.open(req, timeout=25)
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308):
                location = exc.headers.get("Location")
                if not location:
                    raise FetchError("跳转地址为空") from exc
                current = urllib.parse.urljoin(current, location)
                continue
            raise FetchError(f"页面返回 HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise FetchError(f"网络请求失败：{exc.reason}") from exc
        except socket.timeout as exc:
            raise FetchError("网络请求超时") from exc

        raw = resp.read(MAX_PAGE_BYTES + 1)
        if len(raw) > MAX_PAGE_BYTES:
            raise FetchError("页面体积异常")
        content_type = resp.headers.get("Content-Type", "")
        final_url = resp.geturl()
        resp.close()
        return final_url, content_type, raw

    raise FetchError("跳转次数过多")


def decode_html(raw: bytes, content_type: str) -> str:
    match = re.search(r"charset=([\w-]+)", content_type or "", re.I)
    encoding = match.group(1) if match else "utf-8"
    try:
        return raw.decode(encoding, "replace")
    except LookupError:
        return raw.decode("utf-8", "replace")


def pick_text(value) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def photo_id_from(text: str) -> str | None:
    if not text:
        return None
    candidates = [
        r"/short-video/([A-Za-z0-9_-]{6,40})",
        r"/fw/photo/([A-Za-z0-9_-]{6,40})",
        r"/photo/([A-Za-z0-9_-]{6,40})",
        r"[?&]photoId=([A-Za-z0-9_-]{6,40})",
        r'"photoId"\s*:\s*"([A-Za-z0-9_-]{6,40})"',
    ]
    for pattern in candidates:
        found = re.search(pattern, text)
        if found:
            return found.group(1)
    return None


def extract_init_state(html: str) -> dict:
    marker = html.find("window.INIT_STATE")
    if marker < 0:
        raise FetchError("页面里没有找到作品数据（可能需要登录或作品已失效）")
    brace = html.find("{", marker)
    if brace < 0:
        raise FetchError("作品数据格式异常")
    try:
        obj, _ = json.JSONDecoder().raw_decode(html[brace:])
    except json.JSONDecodeError:
        # 兜底：最宽松地截到 </script>
        tail = html[brace:]
        end = tail.find("</script>")
        if end < 0:
            raise FetchError("作品数据解析失败")
        snippet = tail[:end].rstrip().rstrip(";")
        try:
            obj = json.loads(snippet)
        except json.JSONDecodeError as exc:
            raise FetchError("作品数据解析失败") from exc
    if not isinstance(obj, dict):
        raise FetchError("作品数据格式异常")
    return obj


def walk_dicts(node, limit: int = 40000):
    stack = [node]
    seen = 0
    while stack and seen < limit:
        current = stack.pop()
        seen += 1
        if isinstance(current, dict):
            yield current
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def _first_url(items) -> str | None:
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                url = pick_text(item.get("url"))
                if url.startswith("http"):
                    return url
            elif isinstance(item, str) and item.startswith("http"):
                return item
    return None


def _score_photo(node: dict, wanted: str | None) -> int:
    score = 0
    has_video = bool(node.get("manifest")) or bool(node.get("mainMvUrls"))
    if has_video:
        score += 20
    if node.get("photoType") == "VIDEO":
        score += 8
    if pick_text(node.get("caption")):
        score += 3
    if pick_text(node.get("coverUrls")) or node.get("coverUrls"):
        score += 2
    share = json.dumps(node.get("share_info") or "", ensure_ascii=False)
    if wanted:
        if wanted in share:
            score += 40
        if str(node.get("photoId") or "") == wanted:
            score += 60
    return score


def _quality_label(height: int | None, label: str) -> str:
    if label:
        return label
    if not height:
        return "原始画质"
    if height >= 1080:
        return "1080P"
    if height >= 720:
        return "720P"
    if height >= 540:
        return "540P"
    return f"{height}P"


def build_result(node: dict, wanted: str | None) -> dict:
    photo_id_internal = str(node.get("photoId") or "")
    share_info = str(node.get("share_info") or "")
    short_id_match = re.search(r"photoId=([A-Za-z0-9_-]+)", share_info)
    display_id = short_id_match.group(1) if short_id_match else (wanted or photo_id_internal)

    duration_ms = node.get("duration") or 0
    try:
        duration = round(float(duration_ms) / 1000, 3)
    except (TypeError, ValueError):
        duration = 0.0

    cover = _first_url(node.get("coverUrls")) or _first_url(node.get("webpCoverUrls"))

    video = None
    manifest = node.get("manifest") or {}
    reps = []
    for adaptation in manifest.get("adaptationSet") or []:
        for rep in adaptation.get("representation") or []:
            url = pick_text(rep.get("url"))
            if not url.startswith("http"):
                continue
            height = rep.get("height")
            width = rep.get("width")
            codec = pick_text(rep.get("videoCodec")) or "avc"
            bitrate = rep.get("avgBitrate") or 0
            try:
                bitrate = int(bitrate)
            except (TypeError, ValueError):
                bitrate = 0
            try:
                height = int(height)
            except (TypeError, ValueError):
                height = 0
            try:
                width = int(width)
            except (TypeError, ValueError):
                width = 0
            estimate = int(bitrate * 1000 / 8 * duration) if bitrate and duration else 0
            reps.append(
                {
                    "url": url,
                    "backup": _first_url(rep.get("backupUrl")),
                    "width": width,
                    "height": height,
                    "codec": "H.264" if codec.lower() in ("avc", "h264") else codec.upper(),
                    "bitrate": bitrate,
                    "size": estimate,
                    "frameRate": rep.get("frameRate") or 30,
                    "label": _quality_label(height, pick_text(rep.get("qualityLabel"))),
                }
            )

    if reps:
        reps.sort(key=lambda item: (item["height"], item["bitrate"]), reverse=True)
        # 浏览器兼容性优先：同分辨率下优先 H.264
        avc = [item for item in reps if item["codec"] == "H.264"]
        primary = avc[0] if avc else reps[0]
        video = dict(primary)
        video["qualities"] = reps[:6]
    elif node.get("mainMvUrls"):
        main = _first_url(node.get("mainMvUrls"))
        if main:
            video = {
                "url": main,
                "width": 0,
                "height": 0,
                "codec": "MP4",
                "bitrate": 0,
                "size": 0,
                "label": "默认画质",
                "qualities": [],
            }

    if not video:
        raise FetchError("这个作品没有可保存的视频轨道（可能是图集或直播）")

    audio = None
    track = node.get("soundTrack") or {}
    audio_url = _first_url(track.get("audioUrls"))
    if audio_url:
        audio = {
            "url": audio_url,
            "name": pick_text(track.get("name")),
            "artist": pick_text(track.get("artist")),
            "size": 0,
        }
    if not audio:
        # 部分作品把音频放在独立字段里
        audio_url = _first_url(node.get("audioUrls"))
        if audio_url:
            audio = {"url": audio_url, "name": "", "artist": "", "size": 0}

    author = {
        "name": pick_text(node.get("userName")) or "快手用户",
        "avatar": pick_text(node.get("headUrl")) or _first_url(node.get("headUrls")),
        "userId": str(node.get("userId") or ""),
        "kwaiId": pick_text(node.get("kwaiId")),
    }

    def as_int(key):
        try:
            return int(node.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    return {
        "ok": True,
        "kind": "kuaishou",
        "photoId": display_id,
        "photoIdInternal": photo_id_internal,
        "caption": pick_text(node.get("caption")),
        "author": author,
        "cover": cover,
        "duration": duration,
        "stats": {
            "view": as_int("viewCount"),
            "like": as_int("likeCount"),
            "comment": as_int("commentCount"),
            "share": as_int("forwardCount"),
        },
        "video": video,
        "audio": audio,
        "sourceUrl": f"https://www.kuaishou.com/short-video/{display_id}" if display_id else "",
        "fetchedAt": int(time.time()),
    }


def parse_kuaishou(raw_input: str) -> dict:
    text = (raw_input or "").strip()
    if not text:
        raise FetchError("先粘贴一个快手作品链接")

    photo_id = photo_id_from(text)
    final_url = ""
    html = ""

    # 文本里没有 ID 时，先访问链接看跳转结果
    if not photo_id:
        url_match = re.search(r"https?://[^\s\"'<>，。；]+", text)
        if url_match:
            target = url_match.group(0).rstrip("，。；、)")
            final_url, content_type, raw = fetch_page(target)
            html = decode_html(raw, content_type)
            photo_id = photo_id_from(final_url) or photo_id_from(html)
        elif re.fullmatch(r"[A-Za-z0-9_-]{6,40}", text):
            photo_id = text
        else:
            raise FetchError("没有识别到作品链接，请粘贴完整分享文案")

    if not photo_id:
        raise FetchError("没有识别到作品 ID，请换一条分享链接试试")

    canonical = f"https://www.kuaishou.com/short-video/{photo_id}"
    final_url, content_type, raw = fetch_page(canonical)
    html = decode_html(raw, content_type)

    if "INIT_STATE" not in html:
        # 有的链接会落到分享中间页，再试一次移动版域名
        alt = f"https://v.m.chenzhongtech.com/fw/photo/{photo_id}"
        final_url, content_type, raw = fetch_page(alt)
        html = decode_html(raw, content_type)

    state = extract_init_state(html)

    candidates = []
    for node in walk_dicts(state):
        if node.get("photoId") and (node.get("manifest") or node.get("mainMvUrls")):
            candidates.append(node)

    if not candidates:
        raise FetchError("没有解析到作品数据，作品可能已删除或仅自己可见")

    best = max(candidates, key=lambda item: _score_photo(item, photo_id))
    result = build_result(best, photo_id)
    if not result.get("sourceUrl"):
        result["sourceUrl"] = canonical
    return result


class Handler(BaseHTTPRequestHandler):
    server_version = "KSLocal/" + VERSION
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # 安静一点
        if os.environ.get("KS_VERBOSE"):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")

    def _json(self, payload: dict, status: int = 200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path

        if path == "/api/health":
            self._json(
                {
                    "ok": True,
                    "name": "ks-local-engine",
                    "version": VERSION,
                    "python": sys.version.split()[0],
                }
            )
            return

        if path == "/api/info":
            self._json({"ok": True, "root": ROOT, "version": VERSION})
            return

        if path.startswith("/api/"):
            self._json({"ok": False, "message": "未知接口"}, 404)
            return

        if path in ("", "/"):
            path = "/index.html"

        relative = path.lstrip("/")
        target = os.path.realpath(os.path.join(ROOT, relative))
        if not target.startswith(os.path.realpath(ROOT) + os.sep) and target != os.path.realpath(ROOT):
            self._json({"ok": False, "message": "路径不合法"}, 403)
            return
        if not os.path.isfile(target):
            self._json({"ok": False, "message": "文件不存在"}, 404)
            return

        ext = os.path.splitext(target)[1].lower()
        mime = MIME.get(ext, "application/octet-stream")
        try:
            with open(target, "rb") as handle:
                body = handle.read()
        except OSError:
            self._json({"ok": False, "message": "文件读取失败"}, 500)
            return

        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        if ext == ".html":
            self.send_header("Cache-Control", "no-cache")
        else:
            self.send_header("Cache-Control", "public, max-age=3600")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path != "/api/parse":
            self._json({"ok": False, "message": "未知接口"}, 404)
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > 16 * 1024:
            self._json({"ok": False, "message": "请求内容为空"}, 400)
            return

        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
            target = str(payload.get("url") or "")
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json({"ok": False, "message": "请求格式不正确"}, 400)
            return

        try:
            result = parse_kuaishou(target)
        except FetchError as exc:
            self._json({"ok": False, "message": str(exc)})
            return
        except Exception as exc:  # 未预期异常不打断服务
            if os.environ.get("KS_VERBOSE"):
                import traceback

                traceback.print_exc()
            self._json({"ok": False, "message": f"解析失败：{exc}"})
            return

        self._json(result)


def main():
    port = DEFAULT_PORT
    args = [item for item in sys.argv[1:] if not item.startswith("-")]
    if args:
        try:
            port = int(args[0])
        except ValueError:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print("")
    print("  快手作品保存台 · 本地引擎 v" + VERSION)
    print("  " + "-" * 42)
    print("  打开： " + url)
    print("  停止： Ctrl + C")
    print("")
    if "--open" in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
