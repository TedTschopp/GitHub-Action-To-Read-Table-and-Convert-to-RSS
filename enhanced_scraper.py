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
        
        # Generate RSS feed
        RSSGenerator.generate_gai_feed(current_gai_data)
        
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
