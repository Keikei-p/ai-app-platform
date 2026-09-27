from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.parse import urlparse
import ipaddress
import socket
import urllib.request

from .redaction import redact_sensitive
from .research_guard import ResearchGuard


MAX_RESEARCH_BYTES = 512 * 1024
class _GuardedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, validator: Callable[[str], None]):
        super().__init__()
        self._validator = validator

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self._validator(str(newurl))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


ALLOWED_CONTENT_TYPES = (
    "text/plain",
    "text/html",
    "application/json",
    "application/xml",
    "text/xml",
    "text/markdown",
)


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if value:
            self.parts.append(value)

    def text(self) -> str:
        return "\n".join(self.parts)


@dataclass(frozen=True)
class ResearchFetchResult:
    requested_url: str
    final_url: str
    title: str
    content_type: str
    bytes_read: int
    safe_for_reasoning: bool
    quarantine_indicators: tuple[str, ...]
    content: str
    content_hash: str
    retrieved_at: str = ""
    last_modified: str = ""
    etag: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["quarantine_indicators"] = list(self.quarantine_indicators)
        return data


class GuardedResearchProvider:
    """Fetches public HTTPS research sources under strict SSRF/content limits.

    It does not search the web, execute page instructions, persist knowledge,
    access local/private network addresses, or use application secrets.
    """

    def __init__(
        self,
        *,
        guard: ResearchGuard | None = None,
        resolver: Callable[[str], list[str]] | None = None,
        opener: Callable[[urllib.request.Request, int], Any] | None = None,
    ):
        self.guard = guard or ResearchGuard()
        self._resolver = resolver or self._resolve_addresses
        self._opener = opener

    def fetch(self, url: str, *, timeout: int = 15) -> ResearchFetchResult:
        clean_url = str(url or "").strip()
        self._validate_url(clean_url)

        request = urllib.request.Request(
            clean_url,
            headers={
                "User-Agent": "AivyResearch/0.9",
                "Accept": "text/html,text/plain,application/json,application/xml,text/xml,text/markdown",
            },
            method="GET",
        )
        open_fn = self._opener or self._safe_open
        response = open_fn(request, max(1, min(int(timeout), 30)))
        try:
            final_url = str(response.geturl() or clean_url)
            self._validate_url(final_url)
            content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            if content_type and not any(content_type == x for x in ALLOWED_CONTENT_TYPES):
                raise ValueError("unsupported research content type")

            raw = response.read(MAX_RESEARCH_BYTES + 1)
            if len(raw) > MAX_RESEARCH_BYTES:
                raise ValueError("research source exceeds size limit")
            last_modified = redact_sensitive(
                str(response.headers.get("Last-Modified") or "").strip()
            )[:240]
            etag = redact_sensitive(
                str(response.headers.get("ETag") or "").strip()
            )[:240]

            charset = "utf-8"
            try:
                charset = response.headers.get_content_charset() or "utf-8"
            except Exception:
                pass
            text = raw.decode(charset, errors="replace")
        finally:
            try:
                response.close()
            except Exception:
                pass

        normalized = self._normalize_text(text, content_type)
        inspected = self.guard.inspect(
            source_kind="web",
            locator=final_url,
            title=self._title_from_text(text, content_type),
            content=normalized,
        )
        safe_content = redact_sensitive(normalized)[:80_000] if inspected.safe_for_reasoning else ""
        return ResearchFetchResult(
            requested_url=clean_url,
            final_url=final_url,
            title=inspected.title,
            content_type=content_type or "unknown",
            bytes_read=len(raw),
            safe_for_reasoning=inspected.safe_for_reasoning,
            quarantine_indicators=inspected.indicators,
            content=safe_content,
            content_hash=inspected.content_hash,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            last_modified=last_modified,
            etag=etag,
        )

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https":
            raise ValueError("research URL must use https")
        if not parsed.hostname:
            raise ValueError("research URL requires a hostname")
        if parsed.username or parsed.password:
            raise ValueError("research URL credentials are not allowed")
        if parsed.port not in {None, 443}:
            raise ValueError("research URL must use standard https port")

        host = parsed.hostname.strip().lower().rstrip(".")
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
            raise ValueError("local research hosts are blocked")

        addresses = self._resolver(host)
        if not addresses:
            raise ValueError("research hostname did not resolve")
        for value in addresses:
            try:
                ip = ipaddress.ip_address(value)
            except ValueError as exc:
                raise ValueError("invalid resolved research address") from exc
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                raise ValueError("private or local research network targets are blocked")

    @staticmethod
    def _resolve_addresses(host: str) -> list[str]:
        values: list[str] = []
        for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM):
            address = item[4][0]
            if address not in values:
                values.append(address)
        return values

    def _safe_open(self, request: urllib.request.Request, timeout: int):
        opener = urllib.request.build_opener(_GuardedRedirectHandler(self._validate_url))
        return opener.open(request, timeout=timeout)

    @staticmethod
    def _normalize_text(text: str, content_type: str) -> str:
        if content_type == "text/html":
            parser = _TextExtractor()
            parser.feed(text)
            return parser.text()
        return text

    @staticmethod
    def _title_from_text(text: str, content_type: str) -> str:
        if content_type != "text/html":
            return ""
        lower = text.lower()
        start = lower.find("<title")
        if start < 0:
            return ""
        start = lower.find(">", start)
        end = lower.find("</title>", start + 1)
        if start < 0 or end < 0:
            return ""
        return redact_sensitive(text[start + 1 : end].strip())[:240]
