#!/usr/bin/env python3
"""Rebuild asysyams.id from the latest Wayback captures before June 2026.

The implementation deliberately uses only the Python standard library and the
curl executable already available on GitHub-hosted runners. Archived HTML is
preserved as the primary deliverable so the original WordPress/Elementor/Zox
News layout survives, while local links are rewritten for both a custom domain
and GitHub Pages project hosting.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import hashlib
import html
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from xml.sax.saxutils import escape as xml_escape

try:
    import requests
except ImportError:  # GitHub Actions installs requests; local fallback remains curl.
    requests = None


DOMAIN = "asysyams.id"
ORIGIN = f"https://{DOMAIN}"
WAYBACK = "https://web.archive.org"
ROOT = Path(__file__).resolve().parent.parent
USER_AGENT = "AsySyamsArchiveRecovery/1.0 (+https://github.com/adnanyogi88-dev/asysyams.id)"
STATIC_PAGES = {
    "tentang-asy-syams",
    "pelayanan-asy-syams",
    "pendaftaran-anak-di-asy-syams",
    "gabung-kemitraan-sekolah-asy-syams",
    "informasi-tumbuh-kembang-anak",
    "contact-us-asysyams-id",
    "kebijakan-privasi",
}
IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/svg+xml"}
TEXT_MIMES = {
    "text/html",
    "text/css",
    "text/javascript",
    "text/plain",
    "text/xml",
    "application/javascript",
    "application/json",
    "application/rss+xml",
}
DOMAIN_PATTERN = re.compile(
    r"(?:(?:https?:)?//)(?:www\.)?asysyams\.id(?=/)", re.IGNORECASE
)
ATTR_ROOT_PATTERN = re.compile(
    r"(?P<prefix>\b(?:href|src|action|poster|data-src|data-href|data-url)"
    r"\s*=\s*[\"'])/(?P<path>(?!/)[^\"']*)",
    re.IGNORECASE,
)
CSS_ROOT_PATTERN = re.compile(
    r"(?P<prefix>url\(\s*[\"']?)/(?P<path>(?!/)[^\"')]+)", re.IGNORECASE
)
PROTECTED_PATTERN = re.compile(
    r"<script\b[^>]*type\s*=\s*([\"'])application/ld\+json\1[^>]*>.*?</script>"
    r"|<link\b(?=[^>]*\brel\s*=\s*([\"'])(?:canonical|shortlink)\2)[^>]*>"
    r"|<meta\b(?=[^>]*\b(?:property|name)\s*=\s*([\"'])"
    r"(?:og:url|og:image|twitter:image)\3)[^>]*>",
    re.IGNORECASE | re.DOTALL,
)
DIMENSION_PATTERN = re.compile(r"-(\d{2,5})x(\d{2,5})(?=\.[^.]+$)", re.I)
ELEMENTOR_HASH_PATTERN = re.compile(r"-[a-z0-9]{20,}(?=\.[^.]+$)", re.I)
HTTP_SESSIONS = threading.local()


@dataclasses.dataclass(frozen=True)
class Capture:
    timestamp: str
    original: str
    mimetype: str
    digest: str
    original_path: str
    output_path: str


@dataclasses.dataclass
class DownloadResult:
    capture: Capture
    ok: bool
    size: int = 0
    error: str = ""
    attempts: int = 0


def curl(url: str, timeout: int = 100) -> bytes:
    command = [
        "curl",
        "--silent",
        "--show-error",
        "--fail",
        "--location",
        "--compressed",
        "--connect-timeout",
        "20",
        "--max-time",
        str(timeout),
        "--user-agent",
        USER_AGENT,
        url,
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        message = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(message or f"curl exited with status {result.returncode}")
    return result.stdout


def reusable_http_get(url: str, timeout: int = 100) -> bytes:
    """Reuse one HTTPS connection per worker to avoid Archive connection bans."""

    if requests is None:
        return curl(url, timeout=timeout)

    session = getattr(HTTP_SESSIONS, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"})
        adapter = requests.adapters.HTTPAdapter(pool_connections=1, pool_maxsize=1, max_retries=0)
        session.mount("https://", adapter)
        HTTP_SESSIONS.session = session

    try:
        response = session.get(url, timeout=(20, timeout), allow_redirects=True)
        response.raise_for_status()
        return response.content
    except requests.RequestException as error:
        if isinstance(error, requests.ConnectionError):
            session.close()
            HTTP_SESSIONS.session = None
        raise RuntimeError(str(error)) from error


def safe_output_path(original: str, mimetype: str) -> tuple[str, str]:
    parsed = urllib.parse.urlsplit(original)
    host = (parsed.hostname or "").lower()
    if host not in {DOMAIN, f"www.{DOMAIN}"}:
        raise ValueError(f"unsupported host: {host}")

    path = urllib.parse.unquote(parsed.path or "/")
    parts = PurePosixPath(path).parts
    if ".." in parts or ".git" in parts:
        raise ValueError(f"unsafe archived path: {path}")

    if mimetype == "text/html":
        if path == "/":
            output = "index.html"
        elif path.endswith("/"):
            output = f"{path.strip('/')}/index.html"
        elif PurePosixPath(path).suffix.lower() in {".html", ".htm"}:
            output = path.lstrip("/")
        elif PurePosixPath(path).suffix:
            output = path.lstrip("/")
        else:
            output = f"{path.strip('/')}/index.html"
    elif path.endswith("/"):
        extension = {
            "application/json": ".json",
            "application/rss+xml": ".xml",
            "text/xml": ".xml",
        }.get(mimetype, ".txt")
        output = f"{path.strip('/')}/index{extension}" if path != "/" else f"index{extension}"
    else:
        output = path.lstrip("/")

    if not output or output.startswith((".git/", ".github/", "scripts/")):
        raise ValueError(f"reserved archived path: {output}")

    return path, output


def capture_priority(capture: Capture) -> tuple[int, str]:
    path = capture.original_path.strip("/")
    if not path:
        return (0, capture.output_path)
    if path in STATIC_PAGES:
        return (1, capture.output_path)
    if capture.mimetype == "text/css" and (
        "/themes/zox-news" in capture.original_path
        or "/elementor/assets/css/frontend" in capture.original_path
        or "/uploads/elementor/css/" in capture.original_path
    ):
        return (2, capture.output_path)
    if capture.mimetype in IMAGE_MIMES and re.search(r"asysyams|asy.syams|logo", path, re.I):
        return (2, capture.output_path)
    if capture.mimetype == "text/html" and path.count("/") == 0:
        return (3, capture.output_path)
    if capture.mimetype in {"text/css", "application/javascript", "text/javascript"}:
        return (4, capture.output_path)
    if capture.mimetype.startswith("font/") or "font" in capture.mimetype:
        return (5, capture.output_path)
    if capture.mimetype in IMAGE_MIMES:
        return (6, capture.output_path)
    return (7, capture.output_path)


def fetch_inventory(snapshot: str) -> tuple[list[Capture], int, list[dict[str, str]]]:
    base_params = {
        "url": f"{DOMAIN}/*",
        "output": "json",
        "filter": "statuscode:200",
        "fl": "timestamp,original,mimetype,digest",
        "to": snapshot[:8],
    }

    def request_rows(extra: dict[str, str], label: str) -> list[list[str]]:
        params = urllib.parse.urlencode({**base_params, **extra})
        last_error: Exception | None = None
        for attempt in range(1, 5):
            try:
                print(f"Fetching Wayback CDX inventory ({label}, attempt {attempt}/4)...", flush=True)
                return json.loads(curl(f"{WAYBACK}/cdx/search/cdx?{params}", timeout=150))
            except (RuntimeError, json.JSONDecodeError) as error:
                last_error = error
                print(f"CDX inventory retry required: {error}", flush=True)
                if attempt < 4:
                    time.sleep(attempt * 3)
        raise RuntimeError(f"Could not fetch CDX inventory ({label}): {last_error}")

    try:
        rows = request_rows({}, "complete capture history")
    except RuntimeError:
        print("Falling back to the smaller one-capture-per-URL CDX index.", flush=True)
        rows = request_rows({"collapse": "urlkey"}, "collapsed URL index")
    selected: dict[str, Capture] = {}
    skipped: list[dict[str, str]] = []

    for timestamp, original, mimetype, digest in rows[1:]:
        if timestamp > snapshot:
            continue
        try:
            original_path, output_path = safe_output_path(original, mimetype)
        except ValueError as error:
            skipped.append({"url": original, "reason": str(error)})
            continue

        capture = Capture(timestamp, original, mimetype, digest, original_path, output_path)
        existing = selected.get(output_path)
        if existing is None or capture.timestamp > existing.timestamp:
            selected[output_path] = capture

    return sorted(selected.values(), key=capture_priority), len(rows) - 1, skipped


def wayback_raw_url(capture: Capture) -> str:
    return f"{WAYBACK}/web/{capture.timestamp}id_/{capture.original}"


def looks_like_archive_error(capture: Capture, payload: bytes) -> bool:
    if not payload:
        # WordPress ships an intentionally empty mvpcustom.js file. Preserve
        # valid zero-byte assets exactly as archived; only empty HTML is bad.
        return capture.mimetype == "text/html"
    if capture.mimetype != "text/html":
        return False
    sample = payload[:12000].decode("utf-8", "ignore").lower()
    return (
        "wayback machine doesn't have that page archived" in sample
        or "the wayback machine has not archived that url" in sample
        or ("error 429" in sample and "too many requests" in sample)
    )


def download_capture(capture: Capture, attempts: int, refresh: bool) -> DownloadResult:
    destination = ROOT / capture.output_path
    if destination.exists() and destination.stat().st_size > 0 and not refresh:
        return DownloadResult(capture, True, destination.stat().st_size, attempts=0)

    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            payload = reusable_http_get(wayback_raw_url(capture))
            if looks_like_archive_error(capture, payload):
                raise RuntimeError("Wayback returned an empty or unavailable capture")
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + ".restore-tmp")
            temporary.write_bytes(payload)
            temporary.replace(destination)
            return DownloadResult(capture, True, len(payload), attempts=attempt)
        except Exception as error:  # noqa: BLE001 - each resource is retried independently
            last_error = str(error)
            if attempt < attempts:
                time.sleep(min(attempt * 3, 15) + random.uniform(0.2, 1.4))

    return DownloadResult(capture, False, error=last_error, attempts=attempts)


def relative_prefix(output_path: str) -> str:
    depth = len(PurePosixPath(output_path).parts) - 1
    return "../" * depth if depth else "./"


def normalize_image_path(path: str) -> str:
    clean = urllib.parse.unquote(path).split("?", 1)[0]
    clean = clean.replace("/elementor/thumbs/", "/")
    clean = DIMENSION_PATTERN.sub("", clean)
    clean = ELEMENTOR_HASH_PATTERN.sub("", clean)
    clean = re.sub(r"-scaled(?=\.[^.]+$)", "", clean, flags=re.I)
    return clean.lower()


def build_image_aliases(results: list[DownloadResult]) -> dict[str, str]:
    aliases: dict[str, list[str]] = defaultdict(list)
    for result in results:
        if result.ok and result.capture.mimetype in IMAGE_MIMES:
            path = "/" + result.capture.output_path
            aliases[normalize_image_path(path)].append(path)

    chosen: dict[str, str] = {}
    for key, options in aliases.items():
        options.sort(key=lambda value: (bool(DIMENSION_PATTERN.search(value)), len(value)))
        chosen[key] = options[0]
    return chosen


def substitute_missing_images(source: str, known_files: set[str], aliases: dict[str, str]) -> str:
    pattern = re.compile(
        r"(?P<origin>https?://(?:www\.)?asysyams\.id)"
        r"(?P<path>/wp-content/uploads/[^\"'\s<>,)]+\.(?:jpe?g|png|webp|gif|svg))",
        re.I,
    )

    def replace(match: re.Match[str]) -> str:
        requested = urllib.parse.unquote(match.group("path"))
        if requested.lstrip("/") in known_files:
            return match.group(0)
        alternative = aliases.get(normalize_image_path(requested))
        if alternative:
            return match.group("origin") + alternative
        return match.group(0)

    return pattern.sub(replace, source)


RUNTIME_SCRIPT = """
<script id="asysyams-static-recovery-runtime">
(function () {
  'use strict';
  function restoreLazyImages(root) {
    root.querySelectorAll('img[data-src],source[data-src],source[data-srcset]').forEach(function (node) {
      if (node.dataset.src && (!node.getAttribute('src') || node.getAttribute('src').indexOf('data:image/') === 0)) {
        node.setAttribute('src', node.dataset.src);
      }
      if (node.dataset.srcset && !node.getAttribute('srcset')) {
        node.setAttribute('srcset', node.dataset.srcset);
      }
      node.classList.remove('lazyload');
      node.classList.add('lazyloaded');
    });
  }
  function activate() {
    restoreLazyImages(document);
    document.querySelectorAll('form[role="search"],form.search-form').forEach(function (form) {
      form.addEventListener('submit', function (event) {
        var field = form.querySelector('input[name="s"],input[type="search"]');
        if (field && field.value.trim()) {
          event.preventDefault();
          window.location.href = (window.ASYSYAMS_SITE_ROOT || './') + 'search/?q=' + encodeURIComponent(field.value.trim());
        }
      });
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', activate);
  else activate();
  window.addEventListener('load', function () { restoreLazyImages(document); });
})();
</script>
""".strip()


def rewrite_local_links(source: str, output_path: str, inject_runtime: bool) -> str:
    prefix = relative_prefix(output_path)
    protected: dict[str, str] = {}

    def protect(match: re.Match[str]) -> str:
        token = f"__ASYSYAMS_PROTECTED_{len(protected)}__"
        protected[token] = match.group(0)
        return token

    rewritten = PROTECTED_PATTERN.sub(protect, source)
    rewritten = DOMAIN_PATTERN.sub(prefix.rstrip("/"), rewritten)
    rewritten = ATTR_ROOT_PATTERN.sub(lambda m: m.group("prefix") + prefix + m.group("path"), rewritten)
    rewritten = CSS_ROOT_PATTERN.sub(lambda m: m.group("prefix") + prefix + m.group("path"), rewritten)

    for token, original in protected.items():
        rewritten = rewritten.replace(token, original)

    if inject_runtime and "asysyams-static-recovery-runtime" not in rewritten:
        bootstrap = f'<script>window.ASYSYAMS_SITE_ROOT={json.dumps(prefix)};</script>\n{RUNTIME_SCRIPT}\n'
        if re.search(r"</body\s*>", rewritten, re.I):
            rewritten = re.sub(r"</body\s*>", lambda _: bootstrap + "</body>", rewritten, count=1, flags=re.I)
        else:
            rewritten += "\n" + bootstrap

    return rewritten


class MetadataExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.in_title = False
        self.title_parts: list[str] = []
        self.in_first_h1 = False
        self.h1_complete = False
        self.h1_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag == "title" and not self.title_parts:
            self.in_title = True
        if tag == "h1" and not self.h1_complete and "mvp-post-title" in values.get("class", ""):
            self.in_first_h1 = True
        if tag == "meta":
            key = values.get("property") or values.get("name")
            if key and key not in self.meta:
                self.meta[key] = values.get("content", "")
        if tag == "link" and "canonical" in values.get("rel", ""):
            self.meta.setdefault("canonical", values.get("href", ""))

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        if tag == "h1" and self.in_first_h1:
            self.in_first_h1 = False
            self.h1_complete = True

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if self.in_first_h1:
            self.h1_parts.append(data)

    @property
    def title(self) -> str:
        raw = "".join(self.h1_parts) or self.meta.get("og:title") or "".join(self.title_parts)
        return re.sub(r"\s+", " ", raw).strip()


class ArticleBodyExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.capture = False
        self.finished = False
        self.div_depth = 0
        self.ignore_depth = 0
        self.parts: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if not self.capture and not self.finished and tag == "div" and values.get("id") == "mvp-content-main":
            self.capture = True
            self.div_depth = 1
            return
        if not self.capture:
            return
        if tag == "div":
            self.div_depth += 1
        if tag in {"script", "style", "noscript", "iframe"}:
            self.ignore_depth += 1
            return
        if self.ignore_depth:
            return
        if re.fullmatch(r"h[1-6]", tag):
            self.parts.append("\n\n" + "#" * int(tag[1]) + " ")
        elif tag in {"p", "blockquote", "section"}:
            self.parts.append("\n\n")
        elif tag == "br":
            self.parts.append("\n")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag == "a":
            self.links.append(values.get("href", ""))
            self.parts.append("[")
        elif tag == "img":
            src = values.get("data-src") or values.get("src") or ""
            alt = values.get("alt", "")
            if src and not src.startswith("data:"):
                self.parts.append(f"\n\n![{alt}]({src})\n\n")

    def handle_endtag(self, tag: str) -> None:
        if not self.capture:
            return
        if tag in {"script", "style", "noscript", "iframe"} and self.ignore_depth:
            self.ignore_depth -= 1
            return
        if self.ignore_depth:
            return
        if tag == "a" and self.links:
            self.parts.append(f"]({self.links.pop()})")
        elif tag in {"p", "blockquote", "section", "ul", "ol"} or re.fullmatch(r"h[1-6]", tag):
            self.parts.append("\n\n")
        elif tag == "div":
            self.div_depth -= 1
            if self.div_depth <= 0:
                self.capture = False
                self.finished = True

    def handle_data(self, data: str) -> None:
        if self.capture and not self.ignore_depth:
            self.parts.append(data)

    @property
    def markdown(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def quoted_yaml(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def extract_article(source: str, capture: Capture) -> dict[str, Any] | None:
    slug = capture.original_path.strip("/")
    if not slug or "/" in slug or slug in STATIC_PAGES:
        return None

    metadata = MetadataExtractor()
    metadata.feed(source)
    published = metadata.meta.get("article:published_time", "")
    if not published and 'id="mvp-content-main"' not in source and "id='mvp-content-main'" not in source:
        return None

    body = ArticleBodyExtractor()
    body.feed(source)
    title = metadata.title or slug.replace("-", " ").title()
    image = metadata.meta.get("og:image", "")
    description = metadata.meta.get("description") or metadata.meta.get("og:description", "")
    category = metadata.meta.get("article:section", "")
    entry = {
        "title": title,
        "slug": slug,
        "url": f"{ORIGIN}/{slug}/",
        "description": description,
        "date": published,
        "modified": metadata.meta.get("article:modified_time", ""),
        "category": category,
        "image": image,
        "archive_timestamp": capture.timestamp,
        "archive_url": f"{WAYBACK}/web/{capture.timestamp}/{capture.original}",
        "markdown_path": f"content/articles/{slug}.md",
    }

    lines = ["---"]
    for key in ("title", "slug", "description", "date", "modified", "category", "image", "archive_url"):
        lines.append(f"{key}: {quoted_yaml(str(entry[key]))}")
    lines.extend(["---", "", f"# {title}", "", body.markdown or description or title, ""])
    destination = ROOT / entry["markdown_path"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines), encoding="utf-8")
    return entry


def generate_search_page() -> None:
    target = ROOT / "search/index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        """<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Pencarian | Asy-Syams Islamic School</title><meta name="robots" content="noindex,follow"><style>body{font:16px Arial,sans-serif;margin:0;color:#202020;background:#f6f6f6}header{background:#201040;color:#fff;padding:26px max(6vw,20px)}main{max-width:980px;margin:32px auto;padding:0 20px}a{color:#632c91;text-decoration:none}.result{background:#fff;padding:22px;margin:15px 0;border-radius:8px}.result h2{margin:0 0 8px;font-size:20px}.result p{margin:0;color:#626262}</style></head><body><header><a href="../" style="color:white"><strong>Asy-Syams Islamic School</strong></a></header><main><h1 id="heading">Pencarian artikel</h1><div id="results"></div></main><script>const q=(new URLSearchParams(location.search).get('q')||'').trim().toLowerCase();document.getElementById('heading').textContent=q?'Hasil pencarian: '+q:'Pencarian artikel';fetch('../content/articles.json').then(r=>r.json()).then(items=>{const found=items.filter(x=>(x.title+' '+x.description+' '+x.category).toLowerCase().includes(q));document.getElementById('results').innerHTML=found.length?found.slice(0,100).map(x=>'<article class="result"><h2><a href="../'+x.slug+'/">'+x.title+'</a></h2><p>'+x.description+'</p></article>').join(''):'<p>Artikel tidak ditemukan.</p>';});</script></body></html>""",
        encoding="utf-8",
    )


def generate_sitemap(results: list[DownloadResult]) -> None:
    entries: list[tuple[str, str]] = []
    for result in results:
        capture = result.capture
        if not result.ok or capture.mimetype != "text/html":
            continue
        path = capture.original_path
        if path.startswith(("/tag/", "/author/", "/page/", "/wp-")):
            continue
        modified = datetime.strptime(capture.timestamp[:8], "%Y%m%d").date().isoformat()
        entries.append((f"{ORIGIN}{path}", modified))

    entries.sort(key=lambda item: (item[0] != ORIGIN + "/", item[0]))
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for url, last_modified in entries:
        lines.extend(["  <url>", f"    <loc>{xml_escape(url)}</loc>", f"    <lastmod>{last_modified}</lastmod>", "  </url>"])
    lines.append("</urlset>")
    sitemap = ROOT / "sitemap.xml"
    if sitemap.exists():
        original = ROOT / "_archive/original-sitemap.xml"
        original.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sitemap, original)
    sitemap.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ROOT / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {ORIGIN}/sitemap.xml\n", encoding="utf-8"
    )
    (ROOT / ".nojekyll").touch()


def postprocess(results: list[DownloadResult]) -> list[dict[str, Any]]:
    known_files = {result.capture.output_path for result in results if result.ok}
    aliases = build_image_aliases(results)
    articles: list[dict[str, Any]] = []

    for result in results:
        if not result.ok or result.capture.mimetype not in {"text/html", "text/css"}:
            continue
        destination = ROOT / result.capture.output_path
        source = destination.read_text(encoding="utf-8", errors="replace")
        source = substitute_missing_images(source, known_files, aliases)
        if result.capture.mimetype == "text/html":
            article = extract_article(source, result.capture)
            if article:
                articles.append(article)
        rewritten = rewrite_local_links(source, result.capture.output_path, result.capture.mimetype == "text/html")
        destination.write_text(rewritten, encoding="utf-8")

    articles.sort(key=lambda item: (item.get("date", ""), item.get("title", "")), reverse=True)
    article_index = ROOT / "content/articles.json"
    article_index.parent.mkdir(parents=True, exist_ok=True)
    article_index.write_text(json.dumps(articles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    generate_search_page()
    generate_sitemap(results)
    return articles


def write_manifest(
    *,
    snapshot: str,
    capture_count: int,
    results: list[DownloadResult],
    skipped: list[dict[str, str]],
    articles: list[dict[str, Any]],
) -> dict[str, Any]:
    successful = [result for result in results if result.ok]
    failures = [result for result in results if not result.ok]
    mime_counts = Counter(result.capture.mimetype for result in successful)
    summary = {
        "target_snapshot": snapshot,
        "source_captures_examined": capture_count,
        "unique_restore_targets": len(results),
        "restored_resources": len(successful),
        "failed_resources": len(failures),
        "restored_html": mime_counts.get("text/html", 0),
        "restored_images": sum(mime_counts.get(mime, 0) for mime in IMAGE_MIMES),
        "restored_stylesheets": mime_counts.get("text/css", 0),
        "restored_javascript": mime_counts.get("application/javascript", 0) + mime_counts.get("text/javascript", 0),
        "article_count": len(articles),
        "mime_types": dict(sorted(mime_counts.items())),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest = {
        "domain": DOMAIN,
        "snapshot": snapshot,
        "summary": summary,
        "failed": [
            {
                "original": result.capture.original,
                "timestamp": result.capture.timestamp,
                "output": result.capture.output_path,
                "mimetype": result.capture.mimetype,
                "error": result.error,
            }
            for result in failures
        ],
        "skipped": skipped,
        "resources": [
            {
                "original": result.capture.original,
                "timestamp": result.capture.timestamp,
                "output": result.capture.output_path,
                "mimetype": result.capture.mimetype,
                "size": result.size,
                "restored": result.ok,
            }
            for result in results
        ],
    }
    destination = ROOT / "_archive/manifest.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", default="20260611235959", help="Latest permitted Wayback timestamp")
    parser.add_argument("--workers", type=int, default=14, help="Concurrent Wayback download workers")
    parser.add_argument("--attempts", type=int, default=4, help="Attempts for every archived resource")
    parser.add_argument("--limit", type=int, default=0, help="Restore only the first N prioritized resources")
    parser.add_argument("--refresh", action="store_true", help="Replace existing restored files")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not re.fullmatch(r"\d{14}", args.snapshot):
        raise SystemExit("--snapshot must contain exactly 14 digits")

    captures, examined, skipped = fetch_inventory(args.snapshot)
    if args.limit:
        captures = captures[: args.limit]
    print(f"Examined {examined:,} captures and selected {len(captures):,} unique resources.", flush=True)

    results: list[DownloadResult] = []
    totals = Counter()
    lock = threading.Lock()
    started = time.monotonic()

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(download_capture, capture, args.attempts, args.refresh): capture
            for capture in captures
        }
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            results.append(result)
            with lock:
                totals["completed"] += 1
                totals["restored" if result.ok else "failed"] += 1
                totals["bytes"] += result.size
                if totals["completed"] <= 8 or totals["completed"] % 25 == 0 or not result.ok:
                    elapsed = max(time.monotonic() - started, 0.1)
                    print(
                        f"[{totals['completed']:,}/{len(captures):,}] "
                        f"ok={totals['restored']:,} failed={totals['failed']:,} "
                        f"{totals['bytes'] / 1_048_576:.1f}MiB "
                        f"{totals['completed'] / elapsed:.2f}/s "
                        f"{'OK' if result.ok else 'FAILED'} {result.capture.output_path}"
                        + (f" :: {result.error}" if not result.ok else ""),
                        flush=True,
                    )

    results.sort(key=lambda result: capture_priority(result.capture))
    print("Rewriting local links, extracting articles, and rebuilding SEO files...", flush=True)
    articles = postprocess(results)
    summary = write_manifest(
        snapshot=args.snapshot,
        capture_count=examined,
        results=results,
        skipped=skipped,
        articles=articles,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)

    if not (ROOT / "index.html").exists():
        raise SystemExit("Homepage restoration failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
