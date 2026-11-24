"""Fetching the content behind a link: an article from a web page or a full post from X.

- Regular pages: we download the HTML and extract only the article text with the `trafilatura`
  library (it skips menus, footers and ads) as Markdown, so subheadings, lists and tables survive.
  Compared with Defuddle (pydefuddle 0.1.0) and readability on 16 pages on 24.11.2026: trafilatura
  returned as much content or more, and the differences in Defuddle's favour were mostly menus
  and footers (docs/dev/13-tresc-stron.md).
- Posts on X: X shows no content without logging in, so we use the public fxtwitter API
  (full text, including long posts and X articles). When it fails, X's official oEmbed gives
  the beginning of the post.
- When nothing but a link is left after fetching (e.g. a post that only points to an X article),
  we raise FetchError: an error that can be retried is better than a save described as
  "content unavailable".
  Note: in that case the post address is sent to an external service (owner's decision, 19.11.2026).
"""

import html
import re
from dataclasses import dataclass

import httpx
import trafilatura

from app.config import settings

# The most we read from a single page. An article is usually a few hundred KB of HTML.
MAX_BYTES = 5 * 1024 * 1024
TIMEOUT_SECONDS = 20
# Version shown in the User-Agent header.
VERSION = "0.1"


def user_agent(public_url: str) -> str:
    """User-Agent for outgoing requests. With PUBLIC_URL set, it points site owners to this server
    (the usual "+URL" convention for bots); without it, there is no link at all."""
    base = f"Mozilla/5.0 (compatible; Chilli/{VERSION}"
    url = public_url.strip().rstrip("/")
    return f"{base}; +{url})" if url else f"{base})"


# Computed once at import; app/feeds.py uses it as well.
USER_AGENT = user_agent(settings.public_url)

# A post address: x.com or twitter.com, then /user/status/number.
X_HOST = re.compile(r"^https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/")
X_STATUS = re.compile(r"^https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/(\w+)/status/(\d+)")
# The backslash trafilatura puts in Markdown before _, *, [, ] and # (ROW\_NUMBER). We remove it
# so names from code and SQL can be found by search and read normally. The character class is
# deliberately narrow, and code fragments (`...` and ```...```) are left alone: there a backslash
# can be part of the content (\d+\.).
MARKDOWN_ESCAPE = re.compile(r"\\([_*\[\]#])")
CODE_SPAN = re.compile(r"(```.*?```|`[^`\n]*`)", re.S)
# A URL, cut out of the text when checking whether anything besides links is left.
ANY_URL = re.compile(r"https?://\S+")


@dataclass
class FetchedPage:
    """Result of a fetch: the text to save and, if available, the title or author."""

    text: str
    title: str | None = None
    author: str | None = None
    # True when instead of the article we only have more loosely extracted text or the meta
    # description. A screenshot with such a URL then keeps its own text (usually more complete).
    partial: bool = False


class FetchError(Exception):
    """Could not fetch the content behind a link."""


def fetch(url: str, client: httpx.Client | None = None) -> FetchedPage:
    """Fetches the content behind `url`. `client` can be replaced in tests."""
    own_client = client is None
    if client is None:
        client = httpx.Client(
            timeout=TIMEOUT_SECONDS, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )
    try:
        match = X_STATUS.match(url)
        if match:
            page = _fetch_x_post(client, url, user=match.group(1), status_id=match.group(2))
        else:
            page = _fetch_article(client, url)
    finally:
        if own_client:
            client.close()
    if is_only_links(page.text):
        raise FetchError(f"fetched only a link, no content: {url}")
    return page


def is_only_links(text: str | None) -> bool:
    """Whether the text holds nothing but URLs and whitespace (empty text counts too).
    Length is deliberately not checked: a short post is still valid content."""
    return not ANY_URL.sub("", text or "").strip()



def _get(client: httpx.Client, url: str) -> httpx.Response:
    try:
        response = client.get(url)
    except httpx.HTTPError as error:
        raise FetchError(f"{type(error).__name__}: {url}") from error
    if response.status_code != 200:
        raise FetchError(f"HTTP {response.status_code}: {url}")
    if len(response.content) > MAX_BYTES:
        raise FetchError(f"page larger than {MAX_BYTES // 1024 // 1024} MB: {url}")
    return response


def _extract(html_text: str, favor_recall: bool = False) -> str | None:
    """Article text as Markdown, without backslashes before punctuation."""
    text = trafilatura.extract(
        html_text, include_comments=False, favor_recall=favor_recall, output_format="markdown"
    )
    if not text:
        return text
    # split with a group in the pattern returns, alternately: text, code, text, code...
    # (code at odd positions)
    parts = CODE_SPAN.split(text)
    return "".join(part if i % 2 else MARKDOWN_ESCAPE.sub(r"\1", part) for i, part in enumerate(parts))


def _fetch_article(client: httpx.Client, url: str) -> FetchedPage:
    response = _get(client, url)
    text = _extract(response.text)
    metadata = trafilatura.extract_metadata(response.text)
    partial = False
    # X pages (other than a post) show only a generic site description without logging in: we skip
    # the looser attempts there, because they would produce a save with that description instead of an error.
    if is_only_links(text) and not X_HOST.match(url):
        # Second, looser attempt: favor_recall takes more text, sometimes at the cost of junk.
        text = _extract(response.text, favor_recall=True)
        if is_only_links(text) and metadata and metadata.description:
            # Last resort: the page description from meta (og:description). Little, but better than nothing.
            text = metadata.description
        partial = True
    if is_only_links(text):
        raise FetchError(f"no article text found: {url}")
    return FetchedPage(
        text=text,
        title=metadata.title if metadata else None,
        author=metadata.author if metadata else None,
        partial=partial,
    )


def _fetch_x_post(client: httpx.Client, url: str, user: str, status_id: str) -> FetchedPage:
    try:
        data = _get(client, f"https://api.fxtwitter.com/{user}/status/{status_id}").json()
        tweet = data["tweet"]
        author = tweet["author"]
        post = FetchedPage(text=tweet["text"], author=f'{author["name"]} (@{author["screen_name"]})')
        article = _x_article(tweet.get("article"))
    except (FetchError, ValueError, KeyError, TypeError, AttributeError):
        post = None  # the external service failed, below we try the official route
    if post is not None and article is not None:
        return _with_x_article(post, article)
    if post is not None:
        return _with_linked_article(client, post, _external_links(tweet))

    # httpx.URL with params encodes the post address in the query string itself (?, & etc.).
    oembed_url = httpx.URL("https://publish.twitter.com/oembed", params={"omit_script": 1, "url": url})
    data = _get(client, str(oembed_url)).json()
    # oEmbed returns HTML: the post text is in <p>…</p>, lines separated by <br>.
    paragraph = re.search(r"<p[^>]*>(.*?)</p>", data.get("html", ""), re.S)
    if not paragraph:
        raise FetchError(f"no post content: {url}")
    text = re.sub(r"<br\s*/?>", "\n", paragraph.group(1))
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return FetchedPage(text=text, author=data.get("author_name"))


def _external_links(tweet: dict) -> list[str]:
    """Expanded links from the post (fxtwitter gives them in raw_text.facets), without links to X itself."""
    facets = (tweet.get("raw_text") or {}).get("facets") or []
    links = [f.get("replacement", "") for f in facets if f.get("type") == "url"]
    return [link for link in links if link.startswith("http") and not X_HOST.match(link)]


def _with_linked_article(client: httpx.Client, post: FetchedPage, links: list[str]) -> FetchedPage:
    """A post linking to an article: we append the content of the first linked page below the post.
    When the page fails, the post alone remains (that is still a valid save)."""
    if not links:
        return post
    try:
        article = _fetch_article(client, links[0])
    except FetchError:
        return post
    return FetchedPage(
        text=f"{post.text}\n\n--- Content of the linked page ({links[0]}) ---\n{article.text}",
        title=article.title,
        author=post.author,
    )


def _x_article(article: dict | None) -> FetchedPage | None:
    """An X article (long text written on X) from the fxtwitter response: title and content blocks.

    The blocks use the Draft.js editor format: each has a `type` and `text`. Headings are marked
    with `##`, list items with `-`, and an `atomic` block (image, chart) is replaced with its caption
    from `entityMap`. Unknown block types are saved as a plain paragraph, so nothing gets lost.
    """
    if not article:
        return None
    content = article.get("content") or {}
    # entityMap comes as a list of {key: "0", value: {...}}; the keys are strings, but in blocks
    # (entityRanges) they are numbers, so everything is converted to strings for comparison.
    entities = {str(e.get("key")): e.get("value") or {} for e in content.get("entityMap") or []}
    lines: list[str] = []
    for block in content.get("blocks") or []:
        kind = block.get("type", "")
        text = (block.get("text") or "").strip()
        if kind == "atomic":
            for entity_range in block.get("entityRanges") or []:
                caption = ((entities.get(str(entity_range.get("key"))) or {}).get("data") or {}).get("caption")
                if caption:
                    lines.append(f"[Image: {caption}]")
        elif not text:
            continue
        elif kind.startswith("header"):
            lines.append(f"## {text}")
        elif kind == "unordered-list-item":
            lines.append(f"- {text}")
        elif kind == "ordered-list-item":
            lines.append(f"1. {text}")
        elif kind == "blockquote":
            lines.append(f"> {text}")
        else:
            lines.append(text)
    body = "\n\n".join(lines) or (article.get("preview_text") or "")
    if is_only_links(body):
        return None
    title = article.get("title")
    return FetchedPage(text=f"{title}\n\n{body}" if title else body, title=title)


def _with_x_article(post: FetchedPage, article: FetchedPage) -> FetchedPage:
    """A post pointing to an X article: the article content, with the author's comment above it
    if they wrote anything besides the link."""
    text = article.text if is_only_links(post.text) else f"{post.text}\n\n{article.text}"
    return FetchedPage(text=text, title=article.title, author=post.author)
