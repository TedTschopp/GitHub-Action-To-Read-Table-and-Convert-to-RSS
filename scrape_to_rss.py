#!/usr/bin/env python3
"""
GitHub Action script to scrape table data from gaiinsights.com/ratings
and generate an RSS feed.
"""

import json
import hashlib
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
import os
import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def setup_driver():
    """
    Setup Chrome driver with Safari user agent for JavaScript rendering.
    
    Returns:
        webdriver.Chrome: Configured Chrome driver instance
    """
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--remote-debugging-port=9222')
    options.add_argument('--window-size=1920,1080')
    
    # Latest Safari user agent (macOS Sonoma)
    safari_user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
    options.add_argument(f'--user-agent={safari_user_agent}')
    
    # Use system Chrome in GitHub Actions
    if os.environ.get('CHROME_BIN'):
        options.binary_location = os.environ.get('CHROME_BIN')
    
    driver = webdriver.Chrome(options=options)
    return driver

def scrape_table_data(url, table_id):
    """
    Scrape table data from the specified URL and table ID using Selenium for JavaScript rendering.
    
    Args:
        url (str): The URL to scrape
        table_id (str): The ID of the table to scrape
        
    Returns:
        list: List of dictionaries containing table row data
    """
    driver = None
    try:
        print(f"Setting up browser with Safari user agent...")
        driver = setup_driver()
        
        print(f"Fetching data from: {url}")
        driver.get(url)
        
        # Wait for page to load and JavaScript to execute
        print("Waiting for page to load...")
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # Additional wait for dynamic content to load
        print("Waiting for dynamic content...")
        time.sleep(5)
        
        # Try to wait for the specific table
        try:
            print(f"Waiting for table with ID: {table_id}")
            WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.ID, table_id))
            )
        except:
            print(f"Table with ID '{table_id}' not immediately found, proceeding with page source...")
        
        # Get the fully rendered HTML after JavaScript execution
        html_content = driver.page_source
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find the table with the specified ID
        table = soup.find('table', id=table_id)
        if not table:
            print(f"Error: Table with ID '{table_id}' not found on the page")
            # Debug: print available tables
            all_tables = soup.find_all('table')
            print(f"Found {len(all_tables)} tables on the page")
            for i, t in enumerate(all_tables):
                table_id_attr = t.get('id', 'No ID')
                table_class = t.get('class', 'No class')
                print(f"Table {i+1}: ID='{table_id_attr}', Class='{table_class}'")
            return []
        
        print(f"Found table with ID: {table_id}")
        
        # Extract table headers
        headers_row = table.find('thead')
        if headers_row:
            headers = [th.get_text(strip=True) for th in headers_row.find_all(['th', 'td'])]
        else:
            # If no thead, try to get headers from first row
            first_row = table.find('tr')
            if first_row:
                headers = [th.get_text(strip=True) for th in first_row.find_all(['th', 'td'])]
            else:
                headers = []
        
        print(f"Table headers: {headers}")
        
        # Extract table rows
        tbody = table.find('tbody')
        if tbody:
            rows = tbody.find_all('tr')
        else:
            # If no tbody, get all rows except header
            all_rows = table.find_all('tr')
            rows = all_rows[1:] if len(all_rows) > 1 and headers else all_rows
        
        table_data = []
        for row in rows:
            cells = row.find_all(['td', 'th'])
            if cells:
                row_data = {}
                for i, cell in enumerate(cells):
                    header = headers[i] if i < len(headers) else f"Column_{i+1}"
                    # Get text content and any links
                    cell_text = cell.get_text(strip=True)
                    links = [a.get('href') for a in cell.find_all('a', href=True)]
                    
                    row_data[header] = {
                        'text': cell_text,
                        'links': links
                    }
                
                if any(row_data.values()):  # Only add non-empty rows
                    table_data.append(row_data)
        
        print(f"Extracted {len(table_data)} rows from table")
        return table_data
        
    except Exception as e:
        print(f"Error during scraping: {e}")
        return []
    finally:
        if driver:
            driver.quit()

def load_previous_data():
    """
    Load previously scraped data to compare for changes.
    
    Returns:
        dict: Previous data or empty dict if file doesn't exist
    """
    try:
        if os.path.exists('previous_data.json'):
            with open('previous_data.json', 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading previous data: {e}")
    return {}

def save_current_data(data):
    """
    Save current data for future comparison.
    
    Args:
        data (list): Current scraped data
    """
    try:
        with open('previous_data.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving current data: {e}")

def generate_rss_feed(table_data, feed_title="GAI Insights Ratings", feed_description="Latest insights from GAI Insights"):
    """
    Generate RSS feed from table data.
    Expected table structure: Date | Rating | Title | Description
    Note: Rating column is excluded from RSS output
    
    Args:
        table_data (list): List of dictionaries containing table row data
        feed_title (str): Title for the RSS feed
        feed_description (str): Description for the RSS feed
    """
    try:
        # Create feed generator
        fg = FeedGenerator()
        fg.title(feed_title)
        fg.link(href='https://gaiinsights.com/ratings', rel='alternate')
        fg.description(feed_description)
        fg.language('en')
        fg.lastBuildDate(datetime.now(timezone.utc))
        fg.generator('GitHub Action Table Scraper')
        
        # Add items to feed
        for i, row_data in enumerate(table_data):
            fe = fg.add_entry()
            
            # Extract specific columns (excluding Rating)
            date_value = ""
            title_value = ""
            title_url = ""
            description_value = ""
            
            # Get column data by position or name
            columns = list(row_data.items())
            if len(columns) >= 4:
                # Column 1: Date
                date_key, date_data = columns[0]
                date_value = date_data.get('text', '').strip()
                
                # Column 2: Rating (skip this one)
                
                # Column 3: Title (with URL)
                title_key, title_data = columns[2]
                title_value = title_data.get('text', '').strip()
                if title_data.get('links'):
                    title_url = title_data['links'][0]  # Get first link
                
                # Column 4: Description
                desc_key, desc_data = columns[3]
                description_value = desc_data.get('text', '').strip()
            
            # Create RSS entry title (just the title, no date)
            if title_value:
                rss_title = title_value
            else:
                rss_title = f"Entry {i+1}"
            
            # Create RSS entry description (plain text, no HTML)
            rss_description = description_value.strip() if description_value else ""
            
            # Create unique ID based on content (excluding rating)
            content_for_id = f"{date_value}|{title_value}|{description_value}"
            entry_id = hashlib.md5(content_for_id.encode()).hexdigest()
            
            # Set RSS entry properties
            fe.id(entry_id)  # Just the hash, no URL
            fe.title(rss_title)
            fe.description(rss_description)
            
            # Use title URL as the link if available, otherwise use main page
            if title_url:
                fe.link(href=title_url)
            else:
                fe.link(href='https://gaiinsights.com/ratings')
            
            fe.pubDate(datetime.now(timezone.utc))
        
        # Generate and save RSS feed
        rss_str = fg.rss_str(pretty=True)
        with open('rss_feed.xml', 'wb') as f:
            f.write(rss_str)
        
        print(f"RSS feed generated successfully with {len(table_data)} entries")
        
    except Exception as e:
        print(f"Error generating RSS feed: {e}")
        sys.exit(1)

def main():
    """
    Main function to orchestrate the scraping and RSS generation.
    """
    url = "https://gaiinsights.com/ratings"
    table_id = "newsTable"
    
    print("Starting table scraping and RSS generation...")
    
    # Scrape table data
    current_data = scrape_table_data(url, table_id)
    
    if not current_data:
        print("No data found or error occurred during scraping")
        # Still generate an empty RSS feed to maintain consistency
        generate_rss_feed([], "GAI Insights Ratings", "No data available at this time")
        return
    
    # Load previous data for comparison
    previous_data = load_previous_data()
    
    # Check if data has changed
    if current_data == previous_data.get('data', []):
        print("No changes detected in table data")
    else:
        print("Changes detected in table data")
    
    # Save current data
    save_current_data({'data': current_data, 'timestamp': datetime.now(timezone.utc).isoformat()})
    
    # Generate RSS feed
    generate_rss_feed(current_data)
    
    print("Process completed successfully!")

if __name__ == "__main__":
    main()
