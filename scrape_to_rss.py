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
import re
import urllib.parse
from dateutil import parser as date_parser
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

def find_latest_ai_news_post(linkedin_profile_url):
    """
    Find the latest "Artificial Intelligence in the news, Week Ending" post from LinkedIn profile.
    
    Args:
        linkedin_profile_url (str): LinkedIn profile URL
        
    Returns:
        str: URL of the latest AI news post, or None if not found
    """
    driver = None
    try:
        print(f"Searching for latest AI news post on LinkedIn profile: {linkedin_profile_url}")
        driver = setup_driver()
        
        driver.get(linkedin_profile_url)
        
        # Wait for page to load
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # Additional wait for dynamic content
        time.sleep(5)
        
        # Get page source and parse
        html_content = driver.page_source
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Look for posts containing "Artificial Intelligence in the news, Week Ending"
        # This is a simplified approach - LinkedIn's structure may require more specific selectors
        posts = soup.find_all(['span', 'div'], string=re.compile(r'Artificial Intelligence in the news, Week Ending', re.IGNORECASE))
        
        if not posts:
            # Try alternative search patterns
            posts = soup.find_all(string=re.compile(r'Artificial Intelligence in the news', re.IGNORECASE))
        
        for post in posts:
            # Try to find the parent container that might have a link
            parent = post.parent
            while parent and parent.name:
                link = parent.find('a', href=True)
                if link and ('linkedin.com' in link['href'] or 'pulse' in link['href']):
                    article_url = link['href']
                    if not article_url.startswith('http'):
                        article_url = 'https://www.linkedin.com' + article_url
                    print(f"Found potential AI news post: {article_url}")
                    return article_url
                parent = parent.parent
        
        print("No AI news posts found")
        return None
        
    except Exception as e:
        print(f"Error finding LinkedIn post: {e}")
        return None
    finally:
        if driver:
            driver.quit()

def scrape_article_links(article_url):
    """
    Scrape article links from the AI news post.
    
    Args:
        article_url (str): URL of the AI news article
        
    Returns:
        list: List of dictionaries containing title and link
    """
    driver = None
    try:
        print(f"Scraping article links from: {article_url}")
        driver = setup_driver()
        
        driver.get(article_url)
        
        # Wait for page to load
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        time.sleep(5)
        
        html_content = driver.page_source
        soup = BeautifulSoup(html_content, 'html.parser')
        
        article_links = []
        
        # Look for links in the article content
        # This may need adjustment based on the actual structure of the posts
        content_areas = soup.find_all(['div', 'article', 'section'], class_=re.compile(r'content|article|post|body', re.IGNORECASE))
        
        if not content_areas:
            # Fallback: look for all links in the page
            content_areas = [soup]
        
        for area in content_areas:
            links = area.find_all('a', href=True)
            for link in links:
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                # Filter out LinkedIn-specific links and focus on external articles
                if (href and text and 
                    not any(skip in href.lower() for skip in ['linkedin.com', 'javascript:', 'mailto:', '#']) and
                    len(text) > 10 and
                    any(domain in href.lower() for domain in ['.com', '.org', '.net', '.ai', '.co'])):
                    
                    # Clean up the URL
                    if not href.startswith('http'):
                        href = 'https://' + href.lstrip('/')
                    
                    article_links.append({
                        'title': text,
                        'url': href
                    })
        
        # Remove duplicates
        seen_urls = set()
        unique_links = []
        for link in article_links:
            if link['url'] not in seen_urls:
                seen_urls.add(link['url'])
                unique_links.append(link)
        
        print(f"Found {len(unique_links)} unique article links")
        return unique_links
        
    except Exception as e:
        print(f"Error scraping article links: {e}")
        return []
    finally:
        if driver:
            driver.quit()

def extract_article_metadata(url):
    """
    Extract metadata from an article URL.
    
    Args:
        url (str): Article URL
        
    Returns:
        dict: Article metadata including title, description, date, guid
    """
    driver = None
    try:
        print(f"Extracting metadata from: {url}")
        driver = setup_driver()
        
        driver.get(url)
        
        # Wait for page to load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        time.sleep(3)
        
        html_content = driver.page_source
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract title
        title = ""
        title_candidates = [
            soup.find('title'),
            soup.find('h1'),
            soup.find('meta', property='og:title'),
            soup.find('meta', name='twitter:title')
        ]
        
        for candidate in title_candidates:
            if candidate:
                if candidate.name == 'meta':
                    title = candidate.get('content', '').strip()
                else:
                    title = candidate.get_text(strip=True)
                if title:
                    break
        
        # Extract description
        description = ""
        desc_candidates = [
            soup.find('meta', property='og:description'),
            soup.find('meta', name='description'),
            soup.find('meta', name='twitter:description'),
            soup.find('meta', property='description')
        ]
        
        for candidate in desc_candidates:
            if candidate:
                description = candidate.get('content', '').strip()
                if description:
                    break
        
        # If no meta description, try to get first paragraph
        if not description:
            paragraphs = soup.find_all('p')
            for p in paragraphs:
                text = p.get_text(strip=True)
                if len(text) > 50:
                    description = text[:300] + '...' if len(text) > 300 else text
                    break
        
        # Extract publish date
        pub_date = None
        date_candidates = [
            soup.find('meta', property='article:published_time'),
            soup.find('meta', name='publishdate'),
            soup.find('meta', name='date'),
            soup.find('time'),
            soup.find('span', class_=re.compile(r'date|time', re.IGNORECASE)),
            soup.find('div', class_=re.compile(r'date|time', re.IGNORECASE))
        ]
        
        for candidate in date_candidates:
            if candidate:
                if candidate.name == 'meta':
                    date_str = candidate.get('content', '')
                elif candidate.name == 'time':
                    date_str = candidate.get('datetime', '') or candidate.get_text(strip=True)
                else:
                    date_str = candidate.get_text(strip=True)
                
                if date_str:
                    try:
                        pub_date = date_parser.parse(date_str)
                        break
                    except:
                        continue
        
        # Generate GUID
        guid = hashlib.md5(url.encode()).hexdigest()
        
        return {
            'title': title or 'No Title',
            'description': description or 'No description available',
            'url': url,
            'pub_date': pub_date or datetime.now(timezone.utc),
            'guid': guid
        }
        
    except Exception as e:
        print(f"Error extracting metadata from {url}: {e}")
        return {
            'title': 'Error loading article',
            'description': f'Could not load article from {url}',
            'url': url,
            'pub_date': datetime.now(timezone.utc),
            'guid': hashlib.md5(url.encode()).hexdigest()
        }
    finally:
        if driver:
            driver.quit()

def generate_eei_rss_feed(articles, feed_title="EEI AI News", feed_description="AI News from External Sources"):
    """
    Generate RSS feed from EEI article data.
    
    Args:
        articles (list): List of article metadata dictionaries
        feed_title (str): Title for the RSS feed
        feed_description (str): Description for the RSS feed
    """
    try:
        print(f"Generating EEI RSS feed with {len(articles)} articles")
        
        # Create feed generator
        fg = FeedGenerator()
        fg.title(feed_title)
        fg.link(href='https://tedt.org/', rel='alternate')
        fg.description(feed_description)
        fg.language('en')
        fg.lastBuildDate(datetime.now(timezone.utc))
        fg.generator('GitHub Action LinkedIn Article Scraper')
        
        # Add articles to feed
        for i, article in enumerate(articles):
            try:
                fe = fg.add_entry()
                
                fe.id(article['guid'])
                fe.title(article['title'])
                fe.description(article['description'])
                fe.link(href=article['url'])
                fe.pubDate(article['pub_date'])
                
                print(f"Added article {i+1}: {article['title']}")
                
            except Exception as e:
                print(f"Error adding article {i+1} to RSS feed: {e}")
                continue
        
        # Generate and save RSS feed
        rss_str = fg.rss_str(pretty=True)
        with open('eei_ai_rss_feed.xml', 'wb') as f:
            f.write(rss_str)
        
        print(f"EEI RSS feed generated successfully with {len(articles)} entries")
        
    except Exception as e:
        print(f"Error generating EEI RSS feed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

def scrape_eei_and_generate_feed():
    """
    Main function to scrape EEI LinkedIn post and generate RSS feed.
    """
    print("Starting EEI LinkedIn scraping and RSS generation...")
    
    linkedin_profile = "https://www.linkedin.com/in/davidbatz/"
    
    # Step 1: Find the latest AI news post
    latest_post_url = find_latest_ai_news_post(linkedin_profile)
    
    if not latest_post_url:
        print("Could not find latest AI news post")
        # Generate empty RSS feed
        generate_eei_rss_feed([], "EEI AI News", "No AI news posts found")
        return
    
    # Step 2: Extract article links from the post
    article_links = scrape_article_links(latest_post_url)
    
    if not article_links:
        print("No article links found in the post")
        generate_eei_rss_feed([], "EEI AI News", "No articles found in latest post")
        return
    
    # Step 3: Extract metadata from each article
    articles = []
    for i, link in enumerate(article_links[:20]):  # Limit to 20 articles to avoid timeout
        print(f"Processing article {i+1}/{min(len(article_links), 20)}: {link['title']}")
        try:
            metadata = extract_article_metadata(link['url'])
            # Use the original title from LinkedIn if the extracted title seems generic
            if metadata['title'] in ['No Title', 'Error loading article'] and link['title']:
                metadata['title'] = link['title']
            articles.append(metadata)
            
            # Add delay to be respectful to websites
            time.sleep(2)
            
        except Exception as e:
            print(f"Failed to process {link['url']}: {e}")
            continue
    
    # Step 4: Generate RSS feed
    generate_eei_rss_feed(articles)
    
    print("EEI process completed successfully!")

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
