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
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

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
    else:
        # Use webdriver-manager to automatically download ChromeDriver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
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
        
        # Extended wait for dynamic content to load
        print("Waiting for dynamic content...")
        time.sleep(10)  # Increased from 5 to 10 seconds
        
        # Try to wait for table rows to be populated
        try:
            print(f"Waiting for table with ID: {table_id}")
            WebDriverWait(driver, 45).until(  # Increased timeout
                EC.presence_of_element_located((By.CSS_SELECTOR, f"#{table_id} tbody tr"))
            )
            print("Table rows detected, waiting for full content load...")
            time.sleep(5)  # Additional wait for content
        except:
            print(f"Table rows not immediately found, proceeding with page source...")
        
        # Get the fully rendered HTML after JavaScript execution
        html_content = driver.page_source
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Debug: Save HTML content for inspection
        if os.environ.get('DEBUG'):
            with open('debug_page_source.html', 'w', encoding='utf-8') as f:
                f.write(html_content)
            print("Debug: Page source saved to debug_page_source.html")
        
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
        print(f"Number of headers: {len(headers)}")
        
        # Extract table rows - more flexible approach
        tbody = table.find('tbody')
        if tbody:
            rows = tbody.find_all('tr')
        else:
            # If no tbody, get all rows except header
            all_rows = table.find_all('tr')
            rows = all_rows[1:] if len(all_rows) > 1 and headers else all_rows
        
        print(f"Found {len(rows)} table rows")
        
        table_data = []
        for row_idx, row in enumerate(rows):
            cells = row.find_all(['td', 'th'])
            if not cells:
                print(f"Row {row_idx + 1}: No cells found, skipping")
                continue
                
            print(f"Row {row_idx + 1}: Processing {len(cells)} cells")
            
            row_data = {}
            has_content = False
            
            for i, cell in enumerate(cells):
                header = headers[i] if i < len(headers) else f"Column_{i+1}"
                # Get text content and any links
                cell_text = cell.get_text(strip=True)
                links = [a.get('href') for a in cell.find_all('a', href=True)]
                
                row_data[header] = {
                    'text': cell_text,
                    'links': links
                }
                
                # Check if this cell has meaningful content
                if cell_text or links:
                    has_content = True
            
            # More lenient check for adding rows
            if has_content:
                table_data.append(row_data)
                print(f"Row {row_idx + 1}: Added to results")
            else:
                print(f"Row {row_idx + 1}: Skipped (no content)")
        
        print(f"Successfully extracted {len(table_data)} rows from table")
        
        # Debug: Print first few rows
        for i, row in enumerate(table_data[:3]):  # First 3 rows
            print(f"Sample row {i+1}: {row}")
        
        return table_data
        
    except Exception as e:
        print(f"Error during scraping: {e}")
        import traceback
        traceback.print_exc()
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

def generate_rss_feed(table_data, feed_title="AI News", feed_description="The Latest News and Updates on AI and Machine Learning"):
    """
    Generate RSS feed from table data with more flexible column handling.
    
    Args:
        table_data (list): List of dictionaries containing table row data
        feed_title (str): Title for the RSS feed
        feed_description (str): Description for the RSS feed
    """
    try:
        # Create feed generator
        fg = FeedGenerator()
        fg.title(feed_title)
        fg.link(href='https://tedt.org/', rel='alternate')
        fg.description(feed_description)
        fg.language('en')
        fg.lastBuildDate(datetime.now(timezone.utc))
        fg.generator('GitHub Action Table Scraper')
        
        print(f"Generating RSS feed with {len(table_data)} entries")
        
        # Add items to feed
        for i, row_data in enumerate(table_data):
            try:
                fe = fg.add_entry()
                
                # Extract data more flexibly
                columns = list(row_data.items())
                print(f"Entry {i+1}: Processing {len(columns)} columns")
                
                # Initialize values
                date_value = ""
                rating_value = ""
                title_value = ""
                title_url = ""
                description_value = ""
                
                # Handle different column counts more flexibly
                if len(columns) >= 3:  # Minimum: Date, Rating, Title, Description
                    # Try to identify columns by content rather than position
                    for col_name, col_data in columns:
                        col_text = col_data.get('text', '').strip()
                        col_links = col_data.get('links', [])
                        
                        # Date column (first column or contains date-like text)
                        if not date_value and (col_name.lower() in ['date', 'published', 'time'] or 
                                             any(char.isdigit() for char in col_text[:10])):
                            date_value = col_text
                        
                        # Rating column (contains rating keywords)
                        elif not rating_value and (col_name.lower() in ['rating', 'score'] or 
                                                  col_text.lower() in ['essential', 'important', 'optional']):
                            rating_value = col_text
                        
                        # Title column (has links or substantial text)
                        elif not title_value and (col_links or (len(col_text) > 10 and 
                                                               col_name.lower() not in ['rating', 'score'] and
                                                               col_text.lower() not in ['essential', 'important', 'optional'])):
                            title_value = col_text
                            if col_links:
                                title_url = col_links[0]
                        
                        # Description column (longest text content)
                        elif len(col_text) > len(description_value) and col_text.lower() not in ['essential', 'important', 'optional']:
                            description_value = col_text
                
                # Fallback: use available data
                if not title_value and columns:
                    # Use first non-empty text as title
                    for col_name, col_data in columns:
                        if col_data.get('text', '').strip():
                            title_value = col_data['text'].strip()
                            if col_data.get('links'):
                                title_url = col_data['links'][0]
                            break
                
                # Create RSS entry
                rss_title = title_value if title_value else f"Entry {i+1}"
                
                # Add rating tag to title based on rating value
                if rating_value:
                    rating_lower = rating_value.lower()
                    if rating_lower == "essential":
                        rss_title += " [ ! ]"
                    elif rating_lower == "important":
                        rss_title += " [ * ]"
                    elif rating_lower == "optional":
                        rss_title += " [ ~ ]"
                
                rss_description = description_value.strip() if description_value else title_value
                
                # Create unique ID
                content_for_id = f"{date_value}|{rating_value}|{title_value}|{description_value}"
                entry_id = hashlib.md5(content_for_id.encode()).hexdigest()
                
                # Set RSS entry properties
                fe.id(entry_id)
                fe.title(rss_title)
                fe.description(rss_description)
                
                # Set link
                if title_url:
                    fe.link(href=title_url)
                else:
                    fe.link(href='https://tedt.org/')
                
                # Set publication date
                pub_date = datetime.now(timezone.utc)
                if date_value:
                    try:
                        # Try various date formats
                        for date_format in ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%Y-%m-%d %H:%M:%S']:
                            try:
                                pub_date = datetime.strptime(date_value, date_format).replace(tzinfo=timezone.utc)
                                break
                            except ValueError:
                                continue
                    except:
                        pass  # Use current time if date parsing fails
                
                fe.pubDate(pub_date)
                print(f"Entry {i+1}: Added '{rss_title}' to RSS feed")
                
            except Exception as e:
                print(f"Error processing entry {i+1}: {e}")
                continue
        
        # Generate and save RSS feed
        rss_str = fg.rss_str(pretty=True)
        with open('ai_rss_feed.xml', 'wb') as f:
            f.write(rss_str)
        
        # Count entries by counting successful entries processed
        entry_count = len(table_data)
        print(f"RSS feed generated successfully with {entry_count} entries")
        
    except Exception as e:
        print(f"Error generating RSS feed: {e}")
        import traceback
        traceback.print_exc()
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
