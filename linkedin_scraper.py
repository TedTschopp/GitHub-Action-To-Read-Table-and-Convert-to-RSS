#!/usr/bin/env python3
"""LinkedIn AI news scraper and RSS generator (separated from general GAI scraping).

Note: Public, unauthenticated scraping of LinkedIn frequently yields incomplete
or blocked content. This module includes best-effort heuristics but will often
return zero results without an authenticated session or manual post URL.
"""
import hashlib
import os
import re
import time
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from dateutil import parser as date_parser
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


SAFARI_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"


class PlaywrightBrowser:
    def __init__(self, headless=True, user_agent=None, window_size="1920,1080"):
        self.headless = headless
        self.user_agent = user_agent
        self.window_size = window_size
        self._play = None
        self._browser = None
        self._context = None
        self._page = None

    def __enter__(self):
        self._play = sync_playwright().start()
        self._browser = self._play.chromium.launch(headless=self.headless)
        w, h = (int(x) for x in self.window_size.split(','))
        self._context = self._browser.new_context(
            user_agent=self.user_agent,
            viewport={"width": w, "height": h},
            java_script_enabled=True
        )
        self._page = self._context.new_page()
        return self._page

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
        finally:
            if self._play:
                self._play.stop()


def find_latest_ai_news_post(profile_url: str) -> str | None:
    print(f"[LinkedIn] Locating AI news post for profile: {profile_url}")
    candidate_urls = [
        profile_url,
        profile_url.rstrip('/') + '/recent-activity/all/',
        profile_url.rstrip('/') + '/recent-activity/posts/'
    ]
    html_content = ""
    with PlaywrightBrowser(headless=True, user_agent=SAFARI_UA) as page:
        for cand in candidate_urls:
            try:
                print(f"[LinkedIn] Try: {cand}")
                page.goto(cand, timeout=30_000, wait_until="domcontentloaded")
                for _ in range(3):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(2)
                time.sleep(3)
                html_content = page.content()
                if '/posts/' in html_content:
                    break
            except Exception as e:
                print(f"[LinkedIn] Navigation failed: {e}")
                continue

    if not html_content:
        print("[LinkedIn] No HTML content retrieved.")
        return None

    soup = BeautifulSoup(html_content, 'html.parser')
    patterns = [
        r"Artificial Intelligence in the news, Week Ending",
        r"AI News.*Week Ending",
        r"Artificial Intelligence.*news",
        r"AI in the news",
        r"Weekly AI update"
    ]
    found_links: list[str] = []
    for pattern in patterns:
        matches = soup.find_all(string=re.compile(pattern, re.IGNORECASE))
        for m in matches:
            parent = m.parent
            hop = 0
            while parent and parent.name != 'html' and hop < 8:
                post_links = parent.find_all('a', href=re.compile(r'/posts/'))
                for link in post_links:
                    href = link.get('href', '')
                    if href and '/posts/' in href:
                        if not href.startswith('http'):
                            href = 'https://www.linkedin.com' + href
                        found_links.append(href.split('?')[0])
                parent = parent.parent
                hop += 1

    if not found_links:
        print("[LinkedIn] Pattern scan empty, regex fallback...")
        raw_links = re.findall(r"https://www.linkedin.com/posts/[^\"'\s<]+", html_content)
        for rl in raw_links:
            rl = rl.split('?')[0]
            if rl not in found_links:
                found_links.append(rl)

    if found_links:
        uniq = list(dict.fromkeys(found_links))
        print(f"[LinkedIn] Found {len(uniq)} candidate post links; choosing first.")
        return uniq[0]
    print("[LinkedIn] No AI post found (likely blocked).")
    return None


def scrape_article_links(post_url: str) -> list[dict]:
    print(f"[LinkedIn] Extracting article links from post: {post_url}")
    articles: list[dict] = []
    with PlaywrightBrowser(headless=True, user_agent=SAFARI_UA) as page:
        for attempt in range(3):
            try:
                page.goto(post_url, timeout=30_000, wait_until="domcontentloaded")
                for _ in range(2):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(2)
                time.sleep(4)
                html = page.content()
                if any(b in html.lower() for b in ["sign in", "join linkedin"]):
                    print(f"[LinkedIn] Attempt {attempt+1}: blocked / login gate.")
                    time.sleep(3)
                    continue
                soup = BeautifulSoup(html, 'html.parser')
                content_area = soup
                links = content_area.find_all('a', href=True)
                for a in links:
                    href = a.get('href', '')
                    txt = a.get_text(strip=True)
                    if not href or not txt:
                        continue
                    if any(skip in href.lower() for skip in ['linkedin.com', 'javascript:', 'mailto:', '#']):
                        continue
                    if len(txt) < 15:
                        continue
                    if not any(k in txt.lower() for k in [
                        'ai','artificial intelligence','machine learning','ml','neural','algorithm','data','tech','automation','robot','deep learning','nlp','computer','digital'
                    ]):
                        continue
                    if href.startswith('//'):
                        href = 'https:' + href
                    elif not href.startswith('http'):
                        href = 'https://' + href.lstrip('/')
                    articles.append({'title': txt, 'url': href})
                break
            except Exception as e:
                print(f"[LinkedIn] Attempt {attempt+1} failed: {e}")
                time.sleep(3)
    # De-dupe and limit
    uniq = []
    seen = set()
    for item in sorted(articles, key=lambda x: len(x['title']), reverse=True):
        if item['url'] not in seen:
            seen.add(item['url'])
            uniq.append(item)
    print(f"[LinkedIn] Collected {len(uniq)} unique article links")
    return uniq[:20]


def extract_article_metadata(url: str) -> dict:
    print(f"[LinkedIn] Fetching article metadata: {url}")
    # Lightweight approach: single playwright load (JS for meta) else fallback
    title = ''
    description = ''
    pub_date = None
    with PlaywrightBrowser(headless=True, user_agent=SAFARI_UA) as page:
        try:
            page.goto(url, timeout=15_000, wait_until="domcontentloaded")
            time.sleep(2)
            html = page.content()
        except Exception as e:
            print(f"[LinkedIn] Metadata load failed: {e}")
            html = ''
    soup = BeautifulSoup(html, 'html.parser') if html else BeautifulSoup('', 'html.parser')
    # Title
    for cand in [soup.find('meta', property='og:title'), soup.find('meta', name='twitter:title'), soup.find('title'), soup.find('h1')]:
        if cand:
            if cand.name == 'meta':
                title = cand.get('content','').strip()
            else:
                title = cand.get_text(strip=True)
            if title:
                break
    # Description
    for cand in [soup.find('meta', property='og:description'), soup.find('meta', name='description'), soup.find('meta', name='twitter:description')]:
        if cand:
            description = cand.get('content','').strip()
            if description:
                break
    if not description:
        first_p = soup.find('p')
        if first_p:
            t = first_p.get_text(strip=True)
            if t:
                description = t[:300] + ('...' if len(t) > 300 else '')
    # Date
    for cand in [
        soup.find('meta', property='article:published_time'),
        soup.find('meta', name='publishdate'),
        soup.find('meta', name='date'),
        soup.find('time')
    ]:
        if cand:
            if cand.name == 'meta':
                ds = cand.get('content','')
            elif cand.name == 'time':
                ds = cand.get('datetime','') or cand.get_text(strip=True)
            else:
                ds = cand.get_text(strip=True)
            if ds:
                try:
                    pub_date = date_parser.parse(ds)
                    break
                except Exception:
                    continue
    guid = hashlib.md5(url.encode()).hexdigest()
    return {
        'title': title or 'No Title',
        'description': description or 'No description available',
        'url': url,
        'pub_date': pub_date or datetime.now(timezone.utc),
        'guid': guid
    }


def generate_rss(articles: list[dict], feed_title="EEI AI News", feed_description="AI News from External Sources"):
    fg = FeedGenerator()
    fg.title(feed_title)
    fg.link(href='https://tedt.org/', rel='alternate')
    fg.description(feed_description)
    fg.language('en')
    fg.lastBuildDate(datetime.now(timezone.utc))
    fg.generator('GitHub Action LinkedIn Article Scraper')
    for art in articles:
        fe = fg.add_entry()
        fe.id(art['guid'])
        fe.title(art['title'])
        fe.description(art['description'])
        fe.link(href=art['url'])
        fe.pubDate(art['pub_date'])
    rss_str = fg.rss_str(pretty=True)
    with open('eei_ai_rss_feed.xml', 'wb') as f:
        f.write(rss_str)
    print(f"[LinkedIn] RSS generated with {len(articles)} items")


def run(profile_url: str, override_post_url: str | None = None):
    post_url = override_post_url or find_latest_ai_news_post(profile_url)
    if not post_url:
        print('[LinkedIn] No post URL resolved; generating empty feed.')
        generate_rss([])
        return
    links = scrape_article_links(post_url)
    articles = []
    for link in links:
        try:
            meta = extract_article_metadata(link['url'])
            if meta['title'] in ['No Title', 'Error loading article'] and link.get('title'):
                meta['title'] = link['title']
            articles.append(meta)
            time.sleep(1.5)
        except Exception as e:
            print(f"[LinkedIn] Failed metadata for {link['url']}: {e}")
    generate_rss(articles)


if __name__ == '__main__':
    profile = os.environ.get('LINKEDIN_PROFILE', 'https://www.linkedin.com/in/davidbatz/')
    manual_post = os.environ.get('LINKEDIN_POST_URL')
    run(profile, manual_post)
