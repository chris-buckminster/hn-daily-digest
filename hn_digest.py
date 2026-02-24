#!/usr/bin/env python3
"""
HN Daily Digest: generates a PDF of yesterday's top 10 Hacker News posts
with article content and top comments.
"""

import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from readability import Document
from weasyprint import HTML

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path.home() / "Documents" / "hn-digests"
LOG_FILE = OUTPUT_DIR / "hn_digest.log"
ALGOLIA_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
FIREBASE_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{}.json"
MAX_POSTS = 10
MAX_COMMENTS = 5
REQUEST_TIMEOUT = 15

log = logging.getLogger("hn_digest")

# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

DOCUMENT_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    @page {{
        size: A4;
        margin: 0.5in;
        @bottom-center {{
            content: "Page " counter(page) " of " counter(pages);
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            font-size: 8pt;
            color: #aaa;
        }}
    }}

    body {{
        font-family: Georgia, 'Times New Roman', serif;
        font-size: 10.5pt;
        line-height: 1.65;
        color: #2a2a2a;
        background: #fff;
    }}

    /* ========== COVER / TOC ========== */

    .toc {{
        page-break-after: always;
    }}

    .toc-header {{
        text-align: center;
        padding: 30pt 0 20pt 0;
        border-bottom: 3px solid #ff6600;
        margin-bottom: 20pt;
    }}

    .toc-header h1 {{
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-size: 28pt;
        font-weight: 800;
        color: #1a1a1a;
        margin: 0;
        letter-spacing: -0.5pt;
    }}

    .toc-header .toc-subtitle {{
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-size: 11pt;
        color: #ff6600;
        margin-top: 6pt;
        font-weight: 500;
        letter-spacing: 2pt;
        text-transform: uppercase;
    }}

    .toc-list {{
        list-style: none;
        padding: 0;
        margin: 0;
    }}

    .toc-item {{
        display: block;
        padding: 7pt 10pt;
        margin-bottom: 4pt;
        border-radius: 4pt;
        background: #fafafa;
        border-left: 3pt solid transparent;
    }}

    .toc-item:nth-child(odd) {{
        background: #f5f5f5;
    }}

    .toc-item-rank {{
        display: inline-block;
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-size: 9pt;
        font-weight: 700;
        color: #fff;
        background: #ff6600;
        border-radius: 3pt;
        padding: 1pt 5pt;
        margin-right: 6pt;
        min-width: 14pt;
        text-align: center;
    }}

    .toc-item-title {{
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-size: 10pt;
        font-weight: 600;
        color: #1a1a1a;
    }}

    .toc-item-title a {{
        color: #1a1a1a;
        text-decoration: none;
    }}

    .toc-item-meta {{
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-size: 7.5pt;
        color: #999;
        margin-top: 1pt;
        padding-left: 30pt;
    }}

    /* ========== POST SECTIONS ========== */

    .post-section {{
        page-break-before: always;
    }}

    .post-card {{
        border: 1px solid #e0e0e0;
        border-radius: 6pt;
        overflow: hidden;
        margin-bottom: 20pt;
    }}

    .post-card-header {{
        background: linear-gradient(135deg, #ff6600, #ff8533);
        padding: 14pt 16pt;
    }}

    .post-card-header .rank-badge {{
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-size: 8pt;
        font-weight: 700;
        color: rgba(255,255,255,0.85);
        text-transform: uppercase;
        letter-spacing: 1.5pt;
        margin-bottom: 4pt;
    }}

    .post-card-header h1 {{
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-size: 18pt;
        font-weight: 700;
        color: #fff;
        margin: 0;
        line-height: 1.3;
    }}

    .post-card-meta {{
        background: #f8f8f8;
        padding: 8pt 16pt;
        border-bottom: 1px solid #e0e0e0;
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-size: 8.5pt;
        color: #666;
    }}

    .post-card-meta a {{
        color: #ff6600;
        text-decoration: none;
        font-weight: 500;
    }}

    .stat {{
        display: inline-block;
        margin-right: 12pt;
    }}

    .stat-value {{
        font-weight: 700;
        color: #333;
    }}

    /* ========== ARTICLE ========== */

    .article {{
        margin: 20pt 0 24pt 0;
    }}

    .article h2 {{
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-size: 11pt;
        font-weight: 700;
        color: #ff6600;
        text-transform: uppercase;
        letter-spacing: 1pt;
        border-bottom: 2px solid #ff6600;
        padding-bottom: 4pt;
        margin-bottom: 12pt;
    }}

    .article .content {{
        text-align: justify;
    }}

    .article .content img {{
        max-width: 100%;
        height: auto;
        border-radius: 3pt;
    }}

    .article .content p:first-child::first-letter {{
        font-size: 24pt;
        color: #ff6600;
        font-weight: bold;
    }}

    .article .unavailable {{
        font-style: italic;
        color: #999;
        padding: 20pt;
        text-align: center;
        background: #fafafa;
        border: 1px dashed #ddd;
        border-radius: 4pt;
    }}

    /* ========== COMMENTS ========== */

    .comments {{
        margin-top: 24pt;
    }}

    .comments h2 {{
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-size: 11pt;
        font-weight: 700;
        color: #ff6600;
        text-transform: uppercase;
        letter-spacing: 1pt;
        border-bottom: 2px solid #ff6600;
        padding-bottom: 4pt;
        margin-bottom: 12pt;
    }}

    .comment {{
        margin-bottom: 12pt;
        padding: 10pt 14pt;
        background: #fafafa;
        border-left: 3px solid #ff6600;
        border-radius: 0 4pt 4pt 0;
        page-break-inside: avoid;
    }}

    .comment:nth-child(even) {{
        border-left-color: #ffaa66;
    }}

    .comment .comment-meta {{
        font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        font-size: 8pt;
        color: #999;
        margin-bottom: 4pt;
    }}

    .comment .comment-meta strong {{
        color: #444;
        font-weight: 600;
    }}

    .comment .comment-body {{
        font-size: 9.5pt;
        line-height: 1.55;
    }}

    .comment .comment-body p {{
        margin: 3pt 0;
    }}

    .comment .comment-body a {{
        color: #ff6600;
        word-break: break-all;
    }}

    .comment .comment-body pre {{
        font-family: 'Courier New', monospace;
        font-size: 8.5pt;
        background: #f0f0f0;
        padding: 6pt 8pt;
        border-radius: 3pt;
        overflow-wrap: break-word;
        white-space: pre-wrap;
    }}

    .comment .comment-body code {{
        font-family: 'Courier New', monospace;
        font-size: 8.5pt;
        background: #f0f0f0;
        padding: 1pt 3pt;
        border-radius: 2pt;
    }}

</style>
</head>
<body>
{toc}
{sections}
</body>
</html>
"""

SECTION_TEMPLATE = """\
<div class="post-section" id="post-{rank}">
    <div class="post-card">
        <div class="post-card-header">
            <div class="rank-badge">#{rank} of {total}</div>
            <h1>{title}</h1>
        </div>
        <div class="post-card-meta">
            <span class="stat"><span class="stat-value">{points}</span> points</span>
            <span class="stat"><span class="stat-value">{num_comments}</span> comments</span>
            <span class="stat">by <strong>{author}</strong></span>
            | <a href="https://news.ycombinator.com/item?id={story_id}">View on HN</a>
            {url_link}
        </div>
    </div>

    <div class="article">
        <h2>Article</h2>
        {article_section}
    </div>

    <div class="comments">
        <h2>Top {comment_count} Comments</h2>
        {comments_html}
    </div>
</div>
"""

COMMENT_TEMPLATE = """\
<div class="comment">
    <div class="comment-meta">
        <strong>{author}</strong> &middot; {time} &middot; {reply_count} replies
    </div>
    <div class="comment-body">{body}</div>
</div>
"""

TOC_TEMPLATE = """\
<div class="toc">
    <div class="toc-header">
        <h1>Hacker News Daily Digest</h1>
        <div class="toc-subtitle">{date}</div>
    </div>
    <div class="toc-list">
        {toc_entries}
    </div>
</div>
"""

TOC_ENTRY_TEMPLATE = """\
<div class="toc-item">
    <span class="toc-item-rank">{rank}</span>
    <span class="toc-item-title"><a href="#post-{rank}">{title}</a></span>
    <div class="toc-item-meta">{points} points &middot; {num_comments} comments &middot; by {author}</div>
</div>
"""

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------


def setup_logging():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stdout),
        ],
    )


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def _request_with_retry(url, params=None, timeout=REQUEST_TIMEOUT, retries=3):
    """GET request with linear backoff retries."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(1 * (attempt + 1))


# ---------------------------------------------------------------------------
# Step 1: Find yesterday's top posts via Algolia
# ---------------------------------------------------------------------------


def find_top_posts_yesterday(limit=MAX_POSTS):
    today_utc = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    yesterday_start = today_utc - timedelta(days=1)
    yesterday_end = today_utc

    start_ts = int(yesterday_start.timestamp())
    end_ts = int(yesterday_end.timestamp())

    resp = _request_with_retry(
        ALGOLIA_SEARCH_URL,
        params={
            "tags": "story",
            "numericFilters": f"created_at_i>{start_ts},created_at_i<{end_ts}",
            "hitsPerPage": limit,
        },
    )
    data = resp.json()

    if not data.get("hits"):
        log.warning("No stories found for yesterday")
        sys.exit(0)

    posts = []
    for hit in data["hits"][:limit]:
        posts.append({
            "id": hit["objectID"],
            "title": hit["title"],
            "url": hit.get("url"),
            "story_text": hit.get("story_text"),
            "points": hit["points"],
            "num_comments": hit["num_comments"],
            "author": hit["author"],
            "created_at": hit["created_at"],
        })
    return posts


# ---------------------------------------------------------------------------
# Step 2: Fetch the linked article content
# ---------------------------------------------------------------------------


def fetch_article(url):
    if not url:
        return None

    try:
        resp = requests.get(
            url,
            timeout=20,
            headers={"User-Agent": "HN-Daily-Digest/1.0 (personal archival tool)"},
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("Could not fetch article at %s: %s", url, exc)
        return None

    try:
        doc = Document(resp.text)
        summary_html = doc.summary()
    except Exception as exc:
        log.warning("readability failed for %s: %s", url, exc)
        return None

    soup = BeautifulSoup(summary_html, "lxml")
    for tag in soup.find_all(["script", "style", "iframe"]):
        tag.decompose()
    for img in soup.find_all("img"):
        src = img.get("src")
        if src and not src.startswith(("http://", "https://", "data:")):
            img["src"] = urljoin(url, src)

    return {"content_html": str(soup)}


# ---------------------------------------------------------------------------
# Step 3: Fetch top comments via Firebase API
# ---------------------------------------------------------------------------


def fetch_item(item_id):
    url = FIREBASE_ITEM_URL.format(item_id)
    try:
        return _request_with_retry(url, timeout=10).json()
    except requests.RequestException:
        log.warning("Failed to fetch item %s", item_id)
        return None


def fetch_top_comments(story_id, limit=MAX_COMMENTS):
    story = fetch_item(story_id)
    if not story:
        return []

    kid_ids = story.get("kids", [])
    if not kid_ids:
        return []

    # Fetch more than we need in case some are deleted/dead
    batch_ids = kid_ids[: limit + 10]
    comments = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_item, cid): cid for cid in batch_ids}
        for future in as_completed(futures):
            item = future.result()
            if (
                item
                and item.get("type") == "comment"
                and not item.get("deleted")
                and not item.get("dead")
            ):
                comments.append(item)

    # Sort: most replies first, then by HN's own rank order
    position_map = {cid: i for i, cid in enumerate(kid_ids)}
    comments.sort(
        key=lambda c: (
            -len(c.get("kids", [])),
            position_map.get(c["id"], 999),
        )
    )

    return comments[:limit]


# ---------------------------------------------------------------------------
# Step 4: Render HTML and generate PDF
# ---------------------------------------------------------------------------


def render_section(post, article, comments, rank, total):
    # Article section
    if article:
        article_section = f'<div class="content">{article["content_html"]}</div>'
    elif post.get("story_text"):
        article_section = f'<div class="content">{post["story_text"]}</div>'
    else:
        article_section = (
            '<div class="unavailable">'
            "Article content could not be retrieved."
            "</div>"
        )

    # URL link in header
    url_link = ""
    if post.get("url"):
        display_url = post["url"]
        if len(display_url) > 60:
            display_url = display_url[:57] + "..."
        url_link = f' | <a href="{escape(post["url"])}">{escape(display_url)}</a>'

    # Comment blocks
    comment_blocks = []
    for c in comments:
        ts = datetime.fromtimestamp(c["time"], tz=timezone.utc)
        time_str = ts.strftime("%Y-%m-%d %H:%M UTC")
        reply_count = len(c.get("kids", []))
        block = COMMENT_TEMPLATE.format(
            author=escape(c.get("by", "[unknown]")),
            time=time_str,
            reply_count=reply_count,
            body=c.get("text", "<em>[deleted]</em>"),
        )
        comment_blocks.append(block)

    return SECTION_TEMPLATE.format(
        rank=rank,
        total=total,
        title=escape(post["title"]),
        points=post["points"],
        author=escape(post["author"]),
        num_comments=post["num_comments"],
        story_id=post["id"],
        url_link=url_link,
        article_section=article_section,
        comment_count=len(comments),
        comments_html="\n".join(comment_blocks),
    )


def generate_pdf(entries):
    """Generate a single PDF from a list of (post, article, comments) tuples."""
    total = len(entries)
    yesterday = date.today() - timedelta(days=1)

    # Build table of contents
    toc_entries = []
    for i, (post, _article, _comments) in enumerate(entries, start=1):
        toc_entries.append(TOC_ENTRY_TEMPLATE.format(
            rank=i,
            title=escape(post["title"]),
            points=post["points"],
            num_comments=post["num_comments"],
            author=escape(post["author"]),
        ))
    toc = TOC_TEMPLATE.format(
        date=yesterday.strftime("%B %d, %Y"),
        toc_entries="\n".join(toc_entries),
    )

    # Build post sections
    sections = []
    for i, (post, article, comments) in enumerate(entries, start=1):
        sections.append(render_section(post, article, comments, rank=i, total=total))

    html_content = DOCUMENT_TEMPLATE.format(
        toc=toc,
        sections="\n".join(sections),
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{yesterday.isoformat()}.pdf"

    HTML(string=html_content).write_pdf(str(output_path))
    return output_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    setup_logging()

    try:
        log.info("Starting HN Daily Digest generation")

        # 1. Find yesterday's top posts
        posts = find_top_posts_yesterday()
        log.info("Found %d top posts", len(posts))

        # 2. For each post, fetch article + comments
        entries = []
        for i, post in enumerate(posts, start=1):
            log.info(
                "[%d/%d] '%s' (%d points, %d comments)",
                i, len(posts), post["title"], post["points"], post["num_comments"],
            )

            article = None
            if post["url"]:
                article = fetch_article(post["url"])
                if article:
                    log.info("  Article fetched: %d chars", len(article["content_html"]))
                else:
                    log.warning("  Could not extract article content")
            else:
                log.info("  Text post (no external URL)")

            comments = fetch_top_comments(int(post["id"]))
            log.info("  Fetched %d comments", len(comments))

            entries.append((post, article, comments))

        # 3. Generate single PDF with all posts
        output_path = generate_pdf(entries)
        log.info("Done. PDF saved to %s", output_path)

    except Exception:
        log.exception("Fatal error")
        sys.exit(1)


if __name__ == "__main__":
    main()
