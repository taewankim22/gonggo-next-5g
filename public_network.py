"""Bounded public HTTP fetch. DNS is resolved and pinned before each connection."""
from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit, urlunsplit, quote
from urllib.robotparser import RobotFileParser

class AgentError(ValueError):
    pass

MAX_BYTES = 12 * 1024 * 1024
USER_AGENT = "GonggoNextResearchBot/0.1"


@dataclass
class Response:
    url: str
    body: bytes
    content_type: str
    status: int
    headers: dict = field(default_factory=dict)


def canonical_url(url):
    try:
        p = urlsplit(url)
    except (ValueError, TypeError) as exc:
        raise AgentError("잘못된 URL입니다.") from exc
    if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password:
        raise AgentError("공개 HTTP/HTTPS 주소만 사용할 수 있습니다.")
    try:
        port = p.port
    except ValueError as exc:
        raise AgentError("잘못된 URL 포트입니다.") from exc
    if port and port not in (80, 443):
        raise AgentError("웹 포트 80/443만 사용할 수 있습니다.")
    return urlunsplit((p.scheme, p.netloc.lower(), quote(p.path or "/",safe="/%:@!$&'()*+,;=-._~"),
                       quote(p.query,safe="/%?:@!$&'()*+,;=-._~"), ""))


def public_address(host, port):
    try:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise AgentError("도메인 이름을 확인할 수 없습니다.") from exc
    addresses = list(dict.fromkeys(r[4][0] for r in records))
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise AgentError("로컬·사설·예약 IP 주소에는 접근할 수 없습니다.")
    return addresses[0]


def _once(url, limit=MAX_BYTES):
    p = urlsplit(canonical_url(url))
    port = p.port or (443 if p.scheme == "https" else 80)
    addr = public_address(p.hostname, port)
    conn = http.client.HTTPConnection(p.hostname, port=port, timeout=25)
    sock = None
    try:
        sock = socket.create_connection((addr, port), timeout=25)
        if p.scheme == "https":
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=p.hostname)
        conn.sock = sock
        target = urlunsplit(("", "", p.path or "/", p.query, ""))
        conn.request("GET", target, headers={"Host":p.netloc, "User-Agent":USER_AGENT, "Accept-Encoding":"identity"})
        resp = conn.getresponse()
        if resp.getheader("Content-Length", "").isdigit() and int(resp.getheader("Content-Length")) > limit:
            raise AgentError("다운로드 용량 제한을 초과했습니다.")
        body = resp.read(limit + 1)
        if len(body) > limit:
            raise AgentError("다운로드 용량 제한을 초과했습니다.")
        return resp.status, dict((k.lower(),v) for k,v in resp.getheaders()), body
    except (OSError, http.client.HTTPException) as exc:
        raise AgentError(f"웹 접근 실패({type(exc).__name__}). 브라우저에서 확인하거나 원문 파일을 가져오세요.") from exc
    finally:
        conn.close()
        if sock:
            sock.close()


def fetch(url, *, respect_robots=True, limit=MAX_BYTES):
    current = canonical_url(url)
    checked = {}
    for _ in range(6):
        p = urlsplit(current)
        base = f"{p.scheme}://{p.netloc}"
        if respect_robots and base not in checked:
            status, headers, body = _once(base + "/robots.txt", limit=1024*1024)
            if status == 200:
                robots = RobotFileParser()
                robots.parse(body.decode("utf-8", errors="replace").splitlines())
                checked[base] = robots
            elif status not in (404, 410):
                raise AgentError(f"robots.txt 확인 실패(HTTP {status}). 자동 수집을 보류합니다.")
            else:
                checked[base] = None
        if respect_robots and checked[base] is not None and not checked[base].can_fetch(USER_AGENT, current):
            raise AgentError("robots.txt에서 수집을 제한합니다. 공식 API/다른 공식 원문 경로를 사용하세요.")
        status, headers, body = _once(current, limit)
        if status in (301,302,303,307,308):
            if "location" not in headers:
                raise AgentError("리디렉션 대상이 없습니다.")
            current = canonical_url(urljoin(current, headers["location"]))
            continue
        if status != 200:
            raise AgentError(f"HTTP {status}: 접근 제한·오류. 반복 우회하지 않고 공식 API/브라우저 확인이 필요합니다.")
        return Response(current, body, headers.get("content-type", ""), status, headers)
    raise AgentError("리디렉션 횟수 제한을 초과했습니다.")
