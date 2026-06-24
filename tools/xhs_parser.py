"""Xiaohongshu (小红书) Post Parser.

Extracts post content from public XHS note URLs via SSR scraping.
No cookie, no Puppeteer, no signing engine required.
"""

import json
import logging
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

_XHS_URL_PATTERNS = [
    re.compile(r"(https?://www\.xiaohongshu\.com/explore/[^\s,，。！]+)"),
    re.compile(r"(https?://www\.xiaohongshu\.com/note/[^\s,，。！]+)"),
    re.compile(r"(https?://www\.xiaohongshu\.com/discovery/item/[^\s,，。！]+)"),
    re.compile(r"(https?://xhslink\.com/[^\s,，。！]+)"),
    re.compile(r"(xhslink\.com/[^\s,，。！]+)"),
]

_NOTE_ID_PATTERNS = [
    re.compile(r"/(?:explore|note|discovery/item)/([A-Za-z0-9]{12,24})"),
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

_UNAVAILABLE_PAGE_MARKERS = (
    "你访问的页面不见了",
    "页面不见了",
    "帖子不存在",
)


def _is_unavailable_fallback(title: str, body: str) -> bool:
    text = f"{title} {body}".strip()
    return any(marker in text for marker in _UNAVAILABLE_PAGE_MARKERS)


def is_allowed_xhs_url(url: str) -> bool:
    """Return whether a URL belongs to supported XHS hosts."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
      return False
    host = (parsed.hostname or "").lower()
    return host in {"www.xiaohongshu.com", "xhslink.com"}


def extract_xhs_url(text: str) -> Optional[str]:
    """Extract the first XHS URL from arbitrary user input text."""
    text = text.strip()
    for pat in _XHS_URL_PATTERNS:
        m = pat.search(text)
        if m:
            url = m.group(1).rstrip(",，。！ ")
            if url.startswith("xhslink.com"):
                url = "https://" + url
            if is_allowed_xhs_url(url):
                return url
    return None


def _normalize_pasted_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"xhslink\.com/\S+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def extract_note_id(url: str) -> Optional[str]:
    """Extract the note ID from a resolved XHS URL."""
    for pat in _NOTE_ID_PATTERNS:
        m = pat.search(url)
        if m:
            return m.group(1)
    return None


def resolve_short_url(url: str) -> str:
    """Follow redirects on short xhslink.com URLs to get the real URL."""
    if "xhslink.com" not in url:
        return url
    try:
        current = url
        with httpx.Client(follow_redirects=False, timeout=10) as client:
            for _ in range(5):
                resp = client.head(current, headers=_HEADERS)
                if resp.status_code not in {301, 302, 303, 307, 308}:
                    return str(resp.url)
                location = resp.headers.get("location")
                if not location:
                    return str(resp.url)
                next_url = urljoin(str(resp.url), location)
                if not is_allowed_xhs_url(next_url):
                    raise ValueError("小红书短链跳转到了不受支持的地址")
                current = next_url
        return current
    except Exception as e:
        logger.warning("Failed to resolve short URL %s: %s", url, e)
        return url


def fetch_note_ssr(note_id: str) -> dict:
    """Fetch note content from XHS SSR page.

    Public notes embed their data in ``window.__INITIAL_STATE__``
    inside the HTML, so no cookie or auth is needed.
    """
    url = f"https://www.xiaohongshu.com/explore/{note_id}"
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(url, headers=_HEADERS)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        logger.error("SSR fetch failed for %s: %s", note_id, e)
        raise ValueError(f"无法访问小红书帖子: {e}")

    # --- Try __INITIAL_STATE__ first ---
    state_match = re.search(
        r"window\.__INITIAL_STATE__\s*=\s*({.*?})\s*</script>",
        html,
        re.DOTALL,
    )
    if state_match:
        try:
            raw = state_match.group(1).replace("undefined", "null")
            state = json.loads(raw)
            note_map = (
                state.get("note", {})
                .get("noteDetailMap", {})
            )
            note_data = None
            for key, val in note_map.items():
                note_data = val.get("note")
                if note_data:
                    break

            if note_data:
                title = note_data.get("title", "") or note_data.get("displayTitle", "")
                body = note_data.get("desc", "")
                note_type = note_data.get("type", "normal")

                images = []
                image_list = note_data.get("imageList", [])
                for img in image_list:
                    img_url = (
                        img.get("urlDefault", "")
                        or img.get("urlPre", "")
                        or img.get("url", "")
                    )
                    if img_url:
                        images.append(img_url)

                if title or body:
                    return {
                        "title": title,
                        "body": body,
                        "images": images,
                        "noteId": note_id,
                        "type": note_type,
                    }
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("__INITIAL_STATE__ parse failed: %s", e)

    # --- Fallback: meta tags ---
    title = ""
    body = ""
    og_title = re.search(
        r'<meta\s+property="og:title"\s+content="([^"]*)"',
        html,
    )
    og_desc = re.search(
        r'<meta\s+property="og:description"\s+content="([^"]*)"',
        html,
    )
    if og_title:
        title = og_title.group(1)
    if og_desc:
        body = og_desc.group(1)

    # Also try the <title> tag
    if not title:
        title_match = re.search(r"<title>([^<]+)</title>", html)
        if title_match:
            title = title_match.group(1).replace(" - 小红书", "").strip()

    if not title and not body:
        raise ValueError("帖子不存在或已被删除，无法提取内容")
    if _is_unavailable_fallback(title, body) or not body.strip():
        raise ValueError(
            "该笔记当前无法读取正文，可能需要登录、已删除或不是公开笔记；请换公开笔记链接，或粘贴分享文案后再解析"
        )

    return {
        "title": title,
        "body": body,
        "images": [],
        "noteId": note_id,
        "type": "normal",
    }


def extract_xhs_note(link: str) -> dict:
    """Main entry: parse user input and extract XHS note content.

    Parameters
    ----------
    link : str
        Can be a full URL, short URL, or arbitrary text containing a link.

    Returns
    -------
    dict
        ``{ title, body, images, noteId, type }``
    """
    url = extract_xhs_url(link)
    if not url:
        pasted_text = _normalize_pasted_text(link)
        if not pasted_text:
            raise ValueError("未找到有效的小红书链接，请检查输入内容")
        note_suffix = re.sub(r"[^A-Za-z0-9]+", "-", pasted_text[:24]).strip("-")
        return {
            "title": pasted_text[:40],
            "body": pasted_text,
            "images": [],
            "noteId": "pasted-" + (note_suffix or "text"),
            "type": "pasted_text",
        }

    url = resolve_short_url(url)
    if not is_allowed_xhs_url(url):
        raise ValueError("小红书短链跳转到了不受支持的地址")

    note_id = extract_note_id(url)
    if not note_id:
        raise ValueError(f"无法从链接中提取笔记 ID: {url}")

    try:
        return fetch_note_ssr(note_id)
    except ValueError:
        pasted_text = _normalize_pasted_text(link)
        if len(pasted_text) >= 20:
            note_suffix = re.sub(r"[^A-Za-z0-9]+", "-", pasted_text[:24]).strip("-")
            return {
                "title": pasted_text[:40],
                "body": pasted_text,
                "images": [],
                "noteId": "pasted-" + (note_suffix or note_id),
                "type": "pasted_text",
            }
        raise
