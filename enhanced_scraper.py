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
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

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

class WebDriverManager:
    """Context manager for WebDriver instances."""
    
    def __init__(self, config=BROWSER_CONFIG):
        self.config = config
        self.driver = None
    
    def __enter__(self):
        self.driver = self._setup_driver()
        return self.driver
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.driver:
            self.driver.quit()
    
    def _setup_driver(self):
        """Setup Chrome driver with configuration."""
        options = Options()
        
        if self.config["headless"]:
            options.add_argument('--headless')
        
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--remote-debugging-port=9222')
        options.add_argument(f'--window-size={self.config["window_size"]}')
        options.add_argument(f'--user-agent={self.config["user_agent"]}')
        
        # Use system Chrome in GitHub Actions
        if os.environ.get('CHROME_BIN'):
            options.binary_location = os.environ.get('CHROME_BIN')
            driver = webdriver.Chrome(options=options)
        else:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
        
        return driver

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
        
        with WebDriverManager() as driver:
            return self._scrape_with_driver(driver)
    
    def _scrape_with_driver(self, driver):
        """Internal method to scrape with provided driver."""
        try:
            driver.get(self.url)
            
            # Wait for page load
            WebDriverWait(driver, self.config["page_load_timeout"]).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Wait for dynamic content
            time.sleep(self.config["dynamic_content_wait"])
            
            # Wait for table
            try:
                WebDriverWait(driver, 45).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, f"#{self.table_id} tbody tr"))
                )
                time.sleep(5)
            except:
                logger.warning("Table rows not immediately found, proceeding...")
            
            # Parse content
            soup = BeautifulSoup(driver.page_source, 'html.parser')
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
        """Generate RSS feed for GAI Insights data."""
        metadata = RSS_METADATA["gai"]
        filename = RSS_FEED_FILES["gai"]
        
        try:
            fg = FeedGenerator()
            fg.title(metadata["title"])
            fg.link(href=metadata["link"], rel='alternate')
            fg.description(metadata["description"])
            fg.language('en')
            fg.lastBuildDate(datetime.now(timezone.utc))
            fg.generator('GitHub Action RSS Scraper v2.0')
            
            for i, row_data in enumerate(table_data):
                try:
                    fe = fg.add_entry()
                    
                    # Extract data intelligently
                    date_val, rating_val, title_val, title_url, desc_val = RSSGenerator._extract_row_data(row_data)
                    
                    # Create RSS title with rating tag
                    rss_title = title_val or f"Entry {i+1}"
                    if rating_val:
                        rating_lower = rating_val.lower()
                        if rating_lower in RATING_TAGS:
                            rss_title += RATING_TAGS[rating_lower]
                    
                    # Set entry properties
                    content_for_id = f"{date_val}|{rating_val}|{title_val}|{desc_val}"
                    entry_id = hashlib.md5(content_for_id.encode()).hexdigest()
                    
                    fe.id(entry_id)
                    fe.title(rss_title)
                    fe.description(desc_val or title_val)
                    fe.link(href=title_url or metadata["link"])
                    
                    # Set publication date
                    pub_date = RSSGenerator._parse_date(date_val) or datetime.now(timezone.utc)
                    fe.pubDate(pub_date)
                    
                except Exception as e:
                    logger.error(f"Error processing GAI entry {i+1}: {e}")
                    continue
            
            # Save RSS feed
            rss_str = fg.rss_str(pretty=True)
            with open(filename, 'wb') as f:
                f.write(rss_str)
            
            logger.info(f"GAI RSS feed generated with {len(table_data)} entries")
            
        except Exception as e:
            logger.error(f"Error generating GAI RSS feed: {e}")
            raise RSSScraperError(f"GAI RSS generation failed: {e}")
    
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
