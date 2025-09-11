#!/usr/bin/env python3
"""
Enhanced RSS scraper with better error handling and configuration management.
"""

import json
import hashlib
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
import xml.etree.ElementTree as ET
import urllib.request
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse
import requests
import random
import time
import re
from dateutil import parser as date_parser
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# Import configuration
from config import *

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RSSScraperError(Exception):
    """Custom exception for RSS scraper errors."""
    pass

class BrowserManager:
    """Context manager for a Playwright browser page (replaces Selenium WebDriver)."""

    def __init__(self, config=BROWSER_CONFIG):
        self.config = config
        self._play = None
        self._browser = None
        self._context = None
        self._page = None

    def __enter__(self):
        self._play = sync_playwright().start()
        # Use chromium; Playwright bundles compatible browsers (install via 'playwright install --with-deps chromium')
        self._browser = self._play.chromium.launch(headless=self.config.get("headless", True))
        width, height = (int(x) for x in self.config.get("window_size", "1920,1080").split(','))
        self._context = self._browser.new_context(
            user_agent=self.config.get("user_agent"),
            viewport={"width": width, "height": height},
            java_script_enabled=True,
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

class DataPersistence:
    """Handle data persistence and change detection."""
    
    @staticmethod
    def load_previous_data(filename='previous_data.json'):
        """Load previously scraped data."""
        try:
            if Path(filename).exists():
                with open(filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading previous data: {e}")
        return {}
    
    @staticmethod
    def save_current_data(data, filename='previous_data.json'):
        """Save current data for future comparison."""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving current data: {e}")
    
    @staticmethod
    def has_data_changed(current_data, previous_data, key='data'):
        """Check if data has changed since last run."""
        return current_data != previous_data.get(key, [])

class GAIInsightsScraper:
    """Scraper for GAI Insights table data."""
    
    def __init__(self):
        self.url = GAI_INSIGHTS_URL
        self.table_id = GAI_TABLE_ID
        self.config = SCRAPING_CONFIG
    
    def scrape(self):
        """Scrape table data from GAI Insights."""
        logger.info(f"Starting GAI Insights scraping from {self.url}")
        
        with BrowserManager() as page:
            return self._scrape_with_page(page)
    
    def _scrape_with_page(self, page):
        """Internal method to scrape with a Playwright page."""
        try:
            logger.info("Navigating to page via Playwright")
            page.goto(self.url, timeout=self.config["page_load_timeout"] * 1000, wait_until="domcontentloaded")

            # Allow additional JS-driven population
            time.sleep(self.config["dynamic_content_wait"])

            # Try waiting specifically for table rows
            try:
                page.wait_for_selector(f"#{self.table_id} tbody tr", timeout=45_000)
                time.sleep(2)
            except PlaywrightTimeoutError:
                logger.warning("Table rows not immediately found, proceeding with current DOM...")

            html = page.content()
            soup = BeautifulSoup(html, 'html.parser')
            return self._extract_table_data(soup)
        except Exception as e:
            logger.error(f"Error during GAI scraping: {e}")
            raise RSSScraperError(f"GAI scraping failed: {e}")
    
    def _extract_table_data(self, soup):
        """Extract data from the HTML table."""
        table = soup.find('table', id=self.table_id)
        if not table:
            raise RSSScraperError(f"Table with ID '{self.table_id}' not found")
        
        # Extract headers
        headers_row = table.find('thead')
        if headers_row:
            headers = [th.get_text(strip=True) for th in headers_row.find_all(['th', 'td'])]
        else:
            first_row = table.find('tr')
            headers = [th.get_text(strip=True) for th in first_row.find_all(['th', 'td'])] if first_row else []
        
        # Extract rows
        tbody = table.find('tbody')
        rows = tbody.find_all('tr') if tbody else table.find_all('tr')[1:]
        
        table_data = []
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if not cells:
                continue
            
            row_data = {}
            for i, cell in enumerate(cells):
                header = headers[i] if i < len(headers) else f"Column_{i+1}"
                cell_text = cell.get_text(strip=True)
                links = [a.get('href') for a in cell.find_all('a', href=True)]
                
                row_data[header] = {
                    'text': cell_text,
                    'links': links
                }
            
            # Only add rows with content
            if any(data['text'] or data['links'] for data in row_data.values()):
                table_data.append(row_data)
        
        logger.info(f"Successfully extracted {len(table_data)} rows from GAI table")
        return table_data

class RSSGenerator:
    """Generate RSS feeds from scraped data."""
    
    @staticmethod
    def generate_gai_feed(table_data):
        """Generate RSS feed for GAI Insights data with 60-day retention and archiving.

        Behaviour:
        - Keep all rows that are within last 60 days inside primary feed.
        - Move older rows into an archive feed file (appended, de-duplicated by GUID).
        - If dates are unparsable, treat as current run (remain in main feed).
        """
        metadata = RSS_METADATA["gai"]
        main_filename = RSS_FEED_FILES["gai"]
        archive_filename = RSS_FEED_FILES.get("gai_archive", "ai_rss_feed_archive.xml")

        cutoff = datetime.now(timezone.utc).date().toordinal() - 60  # ordinal comparison for speed
        recent_rows = []
        archive_rows = []

        # First pass: classify rows by date (if parseable)
        for row in table_data:
            date_val, rating_val, title_val, title_url, desc_val = RSSGenerator._extract_row_data(row)
            parsed_dt = RSSGenerator._parse_date(date_val)
            if parsed_dt:
                if parsed_dt.date().toordinal() >= cutoff:
                    recent_rows.append(row)
                else:
                    archive_rows.append(row)
            else:
                # Keep in recent if date unknown
                recent_rows.append(row)

        logger.info(f"Retention split: {len(recent_rows)} recent rows, {len(archive_rows)} to archive (from {len(table_data)} total)")

        # Generate main feed
        try:
            fg = FeedGenerator()
            fg.title(metadata["title"])
            fg.link(href=metadata["link"], rel='alternate')
            fg.description(metadata["description"])
            fg.language('en')
            fg.lastBuildDate(datetime.now(timezone.utc))
            fg.generator('GitHub Action RSS Scraper v2.1 (retention)')

            for i, row_data in enumerate(recent_rows):
                try:
                    fe = fg.add_entry()
                    date_val, rating_val, title_val, title_url, desc_val = RSSGenerator._extract_row_data(row_data)
                    rss_title = title_val or f"Entry {i+1}"
                    if rating_val and rating_val.lower() in RATING_TAGS:
                        rss_title += RATING_TAGS[rating_val.lower()]
                    content_for_id = f"{date_val}|{rating_val}|{title_val}|{desc_val}"
                    entry_id = hashlib.md5(content_for_id.encode()).hexdigest()
                    fe.id(entry_id)
                    fe.title(rss_title)
                    fe.description(desc_val or title_val)
                    fe.link(href=title_url or metadata["link"])
                    pub_date = RSSGenerator._parse_date(date_val) or datetime.now(timezone.utc)
                    fe.pubDate(pub_date)
                except Exception as e:
                    logger.error(f"Error processing recent GAI entry {i+1}: {e}")
            with open(main_filename, 'wb') as f:
                f.write(fg.rss_str(pretty=True))
            logger.info(f"GAI RSS feed written: {main_filename} ({len(recent_rows)} entries)")
        except Exception as e:
            logger.error(f"Error generating main GAI RSS feed: {e}")
            raise RSSScraperError(f"GAI RSS generation failed: {e}")

        # Archive handling: load existing archive entries (if file exists) then append new ones and write out
        if archive_rows:
            try:
                existing_archive = []
                if Path(archive_filename).exists():
                    try:
                        # Lightweight parse: collect existing GUIDs to prevent duplication
                        from xml.etree import ElementTree as ET
                        tree = ET.parse(archive_filename)
                        root = tree.getroot()
                        for item in root.findall('.//item'):
                            guid_el = item.find('guid')
                            title_el = item.find('title')
                            link_el = item.find('link')
                            desc_el = item.find('description')
                            pub_el = item.find('pubDate')
                            existing_archive.append({
                                'guid': guid_el.text if guid_el is not None else '',
                                'title': title_el.text if title_el is not None else '',
                                'link': link_el.text if link_el is not None else metadata['link'],
                                'description': desc_el.text if desc_el is not None else '',
                                'pubDate': pub_el.text if pub_el is not None else ''
                            })
                    except Exception as parse_err:
                        logger.warning(f"Could not parse existing archive (will recreate): {parse_err}")

                existing_guids = {a['guid'] for a in existing_archive if a.get('guid')}

                archive_fg = FeedGenerator()
                archive_fg.title(metadata["title"] + " (Archive)")
                archive_fg.link(href=metadata["link"], rel='alternate')
                archive_fg.description("Archived items older than 60 days from GAI Insights feed")
                archive_fg.language('en')
                archive_fg.lastBuildDate(datetime.now(timezone.utc))
                archive_fg.generator('GitHub Action RSS Scraper v2.1 (archive)')

                # Re-add existing archive entries first (preserve history)
                for a in existing_archive:
                    try:
                        fe = archive_fg.add_entry()
                        fe.id(a['guid'])
                        fe.title(a['title'])
                        fe.description(a['description'])
                        fe.link(href=a['link'])
                        if a['pubDate']:
                            fe.pubDate(a['pubDate'])
                    except Exception:
                        continue

                # Append new archive rows
                for row_data in archive_rows:
                    try:
                        date_val, rating_val, title_val, title_url, desc_val = RSSGenerator._extract_row_data(row_data)
                        content_for_id = f"{date_val}|{rating_val}|{title_val}|{desc_val}"
                        entry_id = hashlib.md5(content_for_id.encode()).hexdigest()
                        if entry_id in existing_guids:
                            continue
                        fe = archive_fg.add_entry()
                        rss_title = title_val or "Archived Entry"
                        if rating_val and rating_val.lower() in RATING_TAGS:
                            rss_title += RATING_TAGS[rating_val.lower()]
                        fe.id(entry_id)
                        fe.title(rss_title)
                        fe.description(desc_val or title_val)
                        fe.link(href=title_url or metadata['link'])
                        pub_date = RSSGenerator._parse_date(date_val) or datetime.now(timezone.utc)
                        fe.pubDate(pub_date)
                    except Exception as e:
                        logger.error(f"Error archiving row: {e}")
                        continue

                with open(archive_filename, 'wb') as f:
                    f.write(archive_fg.rss_str(pretty=True))
                logger.info(f"Archive RSS updated: {archive_filename} (total entries: {len(existing_archive) + len(archive_rows)})")
            except Exception as e:
                logger.error(f"Error updating archive feed: {e}")
        else:
            logger.info("No rows exceeded 60-day retention; archive unchanged.")
    
    @staticmethod
    def _extract_row_data(row_data):
        """Extract structured data from a table row."""
        columns = list(row_data.items())
        
        date_value = ""
        rating_value = ""
        title_value = ""
        title_url = ""
        description_value = ""
        
        for col_name, col_data in columns:
            col_text = col_data.get('text', '').strip()
            col_links = col_data.get('links', [])
            
            # Identify columns by content
            if not date_value and (col_name.lower() in ['date', 'published', 'time'] or 
                                 any(char.isdigit() for char in col_text[:10])):
                date_value = col_text
            elif not rating_value and (col_name.lower() in ['rating', 'score'] or 
                                      col_text.lower() in ['essential', 'important', 'optional']):
                rating_value = col_text
            elif not title_value and (col_links or (len(col_text) > 10 and 
                                                   col_name.lower() not in ['rating', 'score'])):
                title_value = col_text
                if col_links:
                    title_url = col_links[0]
            elif len(col_text) > len(description_value):
                description_value = col_text
        
        return date_value, rating_value, title_value, title_url, description_value
    
    @staticmethod
    def _parse_date(date_str):
        """Parse date string to datetime object."""
        if not date_str:
            return None
        
        try:
            for date_format in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y']:
                try:
                    return datetime.strptime(date_str, date_format).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
        except:
            pass
        
        return None

# ---------------- Aggregator Utilities ---------------- #

def load_aggregator_configs():
    """Load aggregation settings from unified 'feeds' list in _config.yml.

    We now treat any entry in feeds with aggregated: true (and enabled != false)
    as an aggregation config. Backward compatibility: if legacy aggregated_feeds
    block still exists, include those too (but unified list takes precedence
    for matching keys).
    """
    results = []
    try:
        site_yaml = Path('_config.yml')
        if not site_yaml.exists():
            return results
        try:
            import yaml
        except ImportError:
            logger.warning("PyYAML not installed; skipping aggregation config load")
            return results
        with open(site_yaml, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}

        # Unified list
        unified = data.get('feeds') or []
        if isinstance(unified, list):
            for raw in unified:
                if not isinstance(raw, dict):
                    continue
                if not raw.get('aggregated'):
                    continue
                if raw.get('enabled') is False:
                    continue
                cfg = dict(AGGREGATED_DEFAULT)
                for k,v in raw.items():
                    cfg[k] = v
                cfg['output'] = (cfg.get('output') or cfg.get('url') or 'aggregated_external.xml').lstrip('/')
                cfg['key'] = raw.get('key') or Path(cfg['output']).stem
                results.append(cfg)

        # Legacy block fallback (only add keys not already present)
        legacy = data.get('aggregated_feeds')
        legacy_list = []
        if isinstance(legacy, dict):
            legacy_list = [legacy]
        elif isinstance(legacy, list):
            legacy_list = legacy
        if legacy_list:
            existing_keys = {r['key'] for r in results if 'key' in r}
            for raw in legacy_list:
                if not isinstance(raw, dict):
                    continue
                temp = dict(AGGREGATED_DEFAULT)
                for k,v in raw.items():
                    temp[k] = v
                temp['output'] = (temp.get('output') or 'aggregated_external.xml').lstrip('/')
                temp['key'] = raw.get('key') or Path(temp['output']).stem
                if temp['key'] not in existing_keys:
                    results.append(temp)
    except Exception as e:
        logger.warning(f"Error loading aggregated feed configs: {e}")
    return results

# Backward compatibility helper (returns first config or default)
def load_aggregator_config():
    configs = load_aggregator_configs()
    return configs[0] if configs else dict(AGGREGATED_DEFAULT)

AGG_CACHE_FILE = 'aggregator_cache.json'
_USER_AGENTS = [
    # A small rotating pool of realistic desktop browser UA strings
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 13_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0'
]

def _load_agg_cache():
    try:
        if Path(AGG_CACHE_FILE).exists():
            with open(AGG_CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load aggregator cache: {e}")
    return { 'sources': {}, 'domain_last_fetch': {} }

def _save_agg_cache(cache):
    try:
        with open(AGG_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        logger.warning(f"Failed to save aggregator cache: {e}")

def polite_delay(policy, domain, cache):
    now = time.time()
    domain_times = cache.setdefault('domain_last_fetch', {})
    last = domain_times.get(domain, 0)
    min_interval = policy.get('per_domain_min_interval', 10)
    wait_needed = last + min_interval - now
    if wait_needed > 0:
        sleep_time = min(wait_needed, min_interval)
        logger.info(f"Respecting per-domain interval for {domain}: sleeping {sleep_time:.2f}s")
        time.sleep(sleep_time)
    # Random base inter-request delay
    base_delay = random.uniform(policy.get('min_delay', 1.0), policy.get('max_delay', 3.0))
    time.sleep(base_delay)
    domain_times[domain] = time.time()

def fetch_rss(url, policy, cache):
    """Fetch RSS politely with rotating UA, conditional requests, retries, backoff, and pacing.

    Returns list of items (dict) or empty list on failure/304.
    """
    src_meta = cache.setdefault('sources', {}).setdefault(url, {})
    # Failure tracking (persisted in cache file):
    #   consecutive_failures: int
    #   last_status: HTTP status code or 'exception'
    #   last_error: string summary of last failure
    #   last_success_ts: epoch seconds of last successful fetch
    # Allow configurable skip threshold (default 5) to avoid wasting time on dead feeds.
    skip_threshold = policy.get('skip_after_failures', 5)
    if src_meta.get('consecutive_failures', 0) >= skip_threshold and not src_meta.get('recent_success_grace'):
        logger.warning(f"Skipping {url} (consecutive failures >= {skip_threshold})")
        src_meta['skipped'] = True
        src_meta['last_classification'] = 'skipped'
        return []
    src_meta.pop('skipped', None)
    headers = {
        'User-Agent': random.choice(_USER_AGENTS),
        'Accept': 'application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'close',
        'Cache-Control': 'no-cache'
    }
    # Conditional headers
    if 'etag' in src_meta:
        headers['If-None-Match'] = src_meta['etag']
    if 'last_modified' in src_meta:
        headers['If-Modified-Since'] = src_meta['last_modified']

    attempts = policy.get('retry_attempts', 3)
    back_base = policy.get('retry_backoff_base', 2)
    jitter = policy.get('retry_jitter', 0.5)
    timeout = policy.get('timeout', 25)
    domain = urlparse(url).hostname or 'unknown'

    polite_delay(policy, domain, cache)

    last_err = None
    session = requests.Session()
    for attempt in range(1, attempts + 1):
        try:
            resp = session.get(url, headers=headers, timeout=timeout)
            status = resp.status_code
            if status == 304:
                logger.info(f"Not modified (304): {url}")
                src_meta['last_status'] = 304
                src_meta['last_error'] = None
                src_meta['last_classification'] = 'not_modified'
                return []
            if status >= 400:
                raise RuntimeError(f"HTTP {status}")
            # Update caching headers
            if 'ETag' in resp.headers:
                src_meta['etag'] = resp.headers['ETag']
            if 'Last-Modified' in resp.headers:
                src_meta['last_modified'] = resp.headers['Last-Modified']
            content = resp.content
            root = ET.fromstring(content)
            channel = root.find('channel') or root
            items = []
            for item in channel.findall('.//item'):
                def _text(tag):
                    el = item.find(tag)
                    return el.text.strip() if el is not None and el.text else ''
                items.append({
                    'title': _text('title'),
                    'link': _text('link'),
                    'description': _text('description') or _text('summary'),
                    'pubDate': _text('pubDate')
                })
            # Success bookkeeping
            src_meta['consecutive_failures'] = 0
            src_meta['last_status'] = status
            src_meta['last_error'] = None
            src_meta['last_success_ts'] = time.time()
            # Provide a one-run grace after recovery so we don't immediately skip again.
            src_meta['recent_success_grace'] = True
            src_meta['last_classification'] = 'success'
            return items
        except Exception as e:
            last_err = e
            logger.warning(f"Fetch attempt {attempt}/{attempts} failed for {url}: {e}")
            if attempt < attempts:
                delay = (back_base ** (attempt - 1)) + random.uniform(0, jitter)
                logger.info(f"Backing off {delay:.2f}s before retry")
                time.sleep(delay)
    # Failure after all attempts
    fail_count = src_meta.get('consecutive_failures', 0) + 1
    src_meta['consecutive_failures'] = fail_count
    src_meta['last_status'] = getattr(last_err, 'status', 'exception') if last_err else 'unknown'
    src_meta['last_error'] = str(last_err) if last_err else 'Unknown failure'
    # Remove grace once we have a failure
    src_meta.pop('recent_success_grace', None)
    # Classification heuristics
    err_l = (src_meta.get('last_error') or '').lower()
    classification = 'other_failure'
    if 'ssl' in err_l:
        classification = 'ssl_error'
    elif 'name or service not known' in err_l or 'nxdomain' in err_l or 'temporary failure in name resolution' in err_l or 'nodename nor servname' in err_l:
        classification = 'dns_error'
    elif isinstance(src_meta.get('last_status'), int):
        try:
            code = int(src_meta['last_status'])
            if 400 <= code < 500:
                classification = 'http_4xx'
            elif 500 <= code < 600:
                classification = 'http_5xx'
        except Exception:
            pass
    if 'parse' in err_l or 'xml' in err_l:
        classification = 'xml_error'
    src_meta['last_classification'] = classification
    logger.error(f"All attempts failed for {url}: {last_err}")
    return []

def parse_pub_date(date_str):
    if not date_str:
        return None
    try:
        return date_parser.parse(date_str)
    except Exception:
        return None

def aggregate_external_feeds(cfg):
    sources = cfg.get('sources', [])
    max_items = int(cfg.get('max_items', 150))
    retention_days = int(cfg.get('retention_days', 60))
    source_attr = (cfg.get('source_attribution') or 'title').lower()
    output_file = cfg.get('output', 'aggregated_external.xml')
    archive_file = cfg.get('archive_output') or output_file.replace('.xml', '_archive.xml')
    if not sources:
        logger.info("No sources configured for aggregation")
        return
    logger.info(f"Aggregating {len(sources)} sources -> {output_file} (retention {retention_days} days) [polite mode]")
    collected = []
    # Shuffle sources to avoid same ordering every run
    shuffled = list(sources)
    random.shuffle(shuffled)
    cache = _load_agg_cache()
    policy = AGGREGATED_FETCH_POLICY
    policy.setdefault('skip_after_failures', 5)
    # Optional fast mode for testing (reduces delays). Activate with FAST_AGGREGATE=1
    if os.getenv('FAST_AGGREGATE'):
        logger.info("FAST_AGGREGATE enabled: using minimal polite delays for test run")
        policy = dict(policy)
        policy['min_delay'] = 0.05
        policy['max_delay'] = 0.15
        policy['per_domain_min_interval'] = 0.2
    health = {
        'total_sources': len(shuffled),
        'attempted': 0,
        'skipped': 0,
        'with_items': 0,
        'failures': 0,
        'recovered': 0,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'details': []
    }
    prune_threshold = int(os.getenv('PRUNE_CONSECUTIVE_THRESHOLD', '3'))
    permanent_classes = {'ssl_error','dns_error'}
    recommended_prune = []
    for src in shuffled:
        logger.info(f"Fetching source: {src}")
        pre_failures = cache.get('sources', {}).get(src, {}).get('consecutive_failures', 0)
        items = fetch_rss(src, policy, cache)
        meta = cache.get('sources', {}).get(src, {})
        if meta.get('skipped'):
            health['skipped'] += 1
            health['details'].append({'url': src, 'status': 'skipped', 'consecutive_failures': meta.get('consecutive_failures', 0)})
            continue
        health['attempted'] += 1
        if items:
            health['with_items'] += 1
            if pre_failures and meta.get('consecutive_failures', 0) == 0:
                health['recovered'] += 1
            logger.info(f"  Retrieved {len(items)} items")
        else:
            if meta.get('consecutive_failures', 0) > 0:
                health['failures'] += 1
            logger.info("  No items returned")
        classification = meta.get('last_classification') or ('ok' if items else 'empty')
        cf = meta.get('consecutive_failures', 0)
        if (classification in permanent_classes and cf >= 1) or cf >= prune_threshold:
            recommended_prune.append(src)
        health['details'].append({
            'url': src,
            'status': 'ok' if items else ('failed' if meta.get('consecutive_failures', 0) > 0 else 'empty'),
            'items': len(items),
            'consecutive_failures': meta.get('consecutive_failures', 0),
            'last_error': meta.get('last_error'),
            'last_status': meta.get('last_status'),
            'classification': classification
        })
        src_host = urlparse(src).hostname or 'source'
        for it in items:
            dt = parse_pub_date(it.get('pubDate')) or datetime.now(timezone.utc)
            guid_basis = f"{it.get('title')}|{it.get('link')}|{dt.isoformat()}"
            guid = hashlib.md5(guid_basis.encode()).hexdigest()
            title_text = it.get('title') or 'Untitled'
            description_text = it.get('description') or ''
            if source_attr == 'title':
                title_text += f" (Source: {src_host})"
            elif source_attr == 'description':
                description_text = f"[Source: {src_host}]\n\n{description_text}" if description_text else f"[Source: {src_host}]"
            collected.append({
                'title': title_text,
                'link': it.get('link') or cfg.get('link'),
                'description': description_text,
                'pubDate': dt,
                'guid': guid
            })
        time.sleep(1)  # polite throttle

    # Deduplicate by GUID
    unique = {c['guid']: c for c in collected}.values()
    # Split by retention
    cutoff_ord = (datetime.now(timezone.utc).date().toordinal() - retention_days)
    recent = []
    archive_additions = []
    for entry in unique:
        if entry['pubDate'].date().toordinal() >= cutoff_ord:
            recent.append(entry)
        else:
            archive_additions.append(entry)

    # Sort & trim recent
    recent_sorted = sorted(recent, key=lambda x: x['pubDate'], reverse=True)[:max_items]
    logger.info(f"Writing {len(recent_sorted)} recent aggregated items; {len(archive_additions)} to archive")
    fg = FeedGenerator()
    fg.title(cfg.get('title'))
    fg.link(href=cfg.get('link'), rel='alternate')
    fg.description(cfg.get('description'))
    fg.language('en')
    fg.lastBuildDate(datetime.now(timezone.utc))
    fg.generator('GitHub Action RSS Aggregator v2 (retention)')
    for entry in recent_sorted:
        fe = fg.add_entry()
        fe.id(entry['guid'])
        fe.title(entry['title'])
        fe.description(entry['description'])
        fe.link(href=entry['link'])
        fe.pubDate(entry['pubDate'])
    with open(output_file, 'wb') as f:
        f.write(fg.rss_str(pretty=True))
    logger.info(f"Aggregated feed written: {output_file}")

    # Archive update
    if archive_additions:
        try:
            existing = []
            existing_guids = set()
            if Path(archive_file).exists():
                try:
                    tree = ET.parse(archive_file)
                    root = tree.getroot()
                    for item in root.findall('.//item'):
                        guid_el = item.find('guid')
                        title_el = item.find('title')
                        link_el = item.find('link')
                        desc_el = item.find('description')
                        pub_el = item.find('pubDate')
                        guid_val = guid_el.text if guid_el is not None else ''
                        existing_guids.add(guid_val)
                        existing.append({
                            'guid': guid_val,
                            'title': title_el.text if title_el is not None else '',
                            'link': link_el.text if link_el is not None else cfg.get('link'),
                            'description': desc_el.text if desc_el is not None else '',
                            'pubDate': pub_el.text if pub_el is not None else ''
                        })
                except Exception as parse_err:
                    logger.warning(f"Could not parse existing aggregated archive; recreating: {parse_err}")
            archive_fg = FeedGenerator()
            archive_fg.title(cfg.get('title') + ' (Archive)')
            archive_fg.link(href=cfg.get('link'), rel='alternate')
            archive_fg.description('Archived aggregated items older than retention window')
            archive_fg.language('en')
            archive_fg.lastBuildDate(datetime.now(timezone.utc))
            archive_fg.generator('GitHub Action RSS Aggregator v2 (archive)')
            # Re-add existing
            for e in existing:
                if not e.get('guid'):
                    continue
                fe = archive_fg.add_entry()
                fe.id(e['guid'])
                fe.title(e['title'])
                fe.description(e['description'])
                fe.link(href=e['link'])
                if e['pubDate']:
                    fe.pubDate(e['pubDate'])
            # Add new
            added = 0
            for entry in archive_additions:
                if entry['guid'] in existing_guids:
                    continue
                fe = archive_fg.add_entry()
                fe.id(entry['guid'])
                fe.title(entry['title'])
                fe.description(entry['description'])
                fe.link(href=entry['link'])
                fe.pubDate(entry['pubDate'])
                added += 1
            with open(archive_file, 'wb') as f:
                f.write(archive_fg.rss_str(pretty=True))
            logger.info(f"Aggregated archive updated: {archive_file} (added {added}, total {len(existing) + added})")
        except Exception as e:
            logger.error(f"Error updating aggregated archive: {e}")
    # Persist cache updates
    _save_agg_cache(cache)
    # Write health summary adjacent to output feed for quick inspection
    try:
        health_file = output_file.replace('.xml', '_health.json')
        with open(health_file, 'w', encoding='utf-8') as hf:
            json.dump(health, hf, indent=2)
        logger.info(f"Health summary written: {health_file} (attempted {health['attempted']}, skipped {health['skipped']}, failures {health['failures']}, recovered {health['recovered']})")
        # Markdown report
        report_file = output_file.replace('.xml', '_report.md')
        with open(report_file, 'w', encoding='utf-8') as rf:
            rf.write(f"# Aggregated Feed Health Report: {output_file}\n\n")
            rf.write(f"Generated: {health['timestamp']} UTC\n\n")
            rf.write(f"- Total sources: {health['total_sources']}\n")
            rf.write(f"- Attempted: {health['attempted']}  Skipped: {health['skipped']}  Failures: {health['failures']}  With Items: {health['with_items']}  Recovered: {health['recovered']}\n")
            rf.write(f"- Prune threshold: {prune_threshold} consecutive failures (permanent classes: ssl_error,dns_error)\n\n")
            if recommended_prune:
                rf.write("## Recommended Prune Candidates\n\n")
                for u in recommended_prune:
                    meta = cache['sources'].get(u, {})
                    rf.write(f"- {u} (cf={meta.get('consecutive_failures',0)}, class={meta.get('last_classification')}, last_error={ (meta.get('last_error') or '')[:100] })\n")
                rf.write('\n')
            rf.write("## Source Details (first 100)\n\n")
            rf.write("| URL | Status | Class | CF | Items | Last Status | Error Excerpt |\n")
            rf.write("|-----|--------|-------|----|-------|-------------|---------------|\n")
            for d in health['details'][:100]:
                err_excerpt = (d.get('last_error') or '')[:60].replace('\n',' ')
                rf.write(f"| {d['url']} | {d['status']} | {d.get('classification','')} | {d['consecutive_failures']} | {d['items']} | {d.get('last_status')} | {err_excerpt} |\n")
        logger.info(f"Markdown report written: {report_file}")
        # Skipped sources summary
        skipped_sources = [u for u,m in cache.get('sources',{}).items() if m.get('skipped')]
        with open('skipped_sources.json','w',encoding='utf-8') as sf:
            json.dump({ 'generated': health['timestamp'], 'skip_threshold': policy.get('skip_after_failures'), 'sources': skipped_sources }, sf, indent=2)
        logger.info("Skipped sources summary written: skipped_sources.json")
    except Exception as he:
        logger.warning(f"Failed to write health summary: {he}")

def main():
    """Main execution function."""
    logger.info("Starting enhanced RSS scraper")
    
    try:
        # Initialize components
        persistence = DataPersistence()
        gai_scraper = GAIInsightsScraper()
        
        # Load previous data
        previous_data = persistence.load_previous_data()
        
        # Scrape GAI Insights
        logger.info("=" * 60)
        logger.info("SCRAPING GAI INSIGHTS")
        logger.info("=" * 60)
        
        current_gai_data = gai_scraper.scrape()
        
        # Check for changes
        if persistence.has_data_changed(current_gai_data, previous_data, 'gai_data'):
            logger.info("Changes detected in GAI data")
        else:
            logger.info("No changes detected in GAI data")
        
        # Generate primary GAI feed
        RSSGenerator.generate_gai_feed(current_gai_data)

        # Aggregated external feeds (multi-feed support)
        try:
            aggregator_cfgs = load_aggregator_configs()
            if not aggregator_cfgs:
                logger.info("No aggregated feeds configured")
            else:
                for cfg in aggregator_cfgs:
                    if not cfg.get('enabled', True):
                        logger.info(f"Aggregator '{cfg.get('key')}' disabled")
                        continue
                    logger.info("=" * 60)
                    logger.info(f"AGGREGATING SOURCES FOR FEED: {cfg.get('key')} -> {cfg.get('output')}")
                    logger.info("=" * 60)
                    aggregate_external_feeds(cfg)
        except Exception as agg_err:
            logger.error(f"Aggregator(s) failed: {agg_err}")
        
        # Save current data
        current_data = {
            'gai_data': current_gai_data,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        persistence.save_current_data(current_data)
        
        logger.info("RSS scraper completed successfully")
        
    except Exception as e:
        logger.error(f"Fatal error in RSS scraper: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

if __name__ == "__main__":
    main()
