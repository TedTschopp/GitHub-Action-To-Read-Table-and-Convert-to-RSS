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
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

class PlaywrightBrowser:
    """Context manager encapsulating a Playwright page for scraping."""
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
        width, height = (int(x) for x in self.window_size.split(','))
        self._context = self._browser.new_context(
            user_agent=self.user_agent,
            viewport={"width": width, "height": height},
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

def scrape_table_data(url, table_id):
    """
    Scrape table data from the specified URL and table ID using Selenium for JavaScript rendering.
    
    Args:
        url (str): The URL to scrape
        table_id (str): The ID of the table to scrape
        
    Returns:
        list: List of dictionaries containing table row data
    """
    page = None
    try:
        print("Launching Playwright browser (chromium)...")
        safari_user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
        with PlaywrightBrowser(headless=True, user_agent=safari_user_agent) as page:
            print(f"Fetching data from: {url}")
            page.goto(url, timeout=30_000, wait_until="domcontentloaded")
            print("Waiting for dynamic content (JS)...")
            time.sleep(10)
            try:
                page.wait_for_selector(f"#{table_id} tbody tr", timeout=45_000)
                print("Table rows detected, allowing extra settling time...")
                time.sleep(5)
            except PlaywrightTimeoutError:
                print("Timeout waiting for table rows; proceeding with current DOM.")
            html_content = page.content()
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
        pass

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

def find_latest_ai_news_post(profile_url):
    """
    Find the latest AI news post from a LinkedIn profile with improved selectors.
    
    Args:
        profile_url (str): LinkedIn profile URL
        
    Returns:
        str: URL of the latest AI news post, or None if not found
    """
    # Simplified: Use Playwright for dynamic LinkedIn load (if accessible) otherwise fallback to requests
    page = None
    try:
        print(f"Searching for latest AI news post on LinkedIn profile: {profile_url}")
        # NOTE: LinkedIn aggressively blocks automated scraping; this may fail without auth.
        safari_user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
        with PlaywrightBrowser(headless=True, user_agent=safari_user_agent) as page:
            page.goto(profile_url, timeout=30_000, wait_until="domcontentloaded")
            time.sleep(10)
            html_content = page.content()
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Debug: Save LinkedIn page for inspection
        if os.environ.get('DEBUG'):
            with open('debug_linkedin_page.html', 'w', encoding='utf-8') as f:
                f.write(html_content)
        
        # Multiple search patterns for AI news posts
        search_patterns = [
            r"Artificial Intelligence in the news, Week Ending",
            r"AI News.*Week Ending",
            r"Artificial Intelligence.*news",
            r"AI in the news",
            r"Weekly AI update"
        ]
        
        found_links = []
        
        # Look for posts with these patterns
        for pattern in search_patterns:
            print(f"Searching with pattern: {pattern}")
            matches = soup.find_all(string=re.compile(pattern, re.IGNORECASE))
            print(f"Found {len(matches)} text matches for pattern: {pattern}")
            
            for match in matches:
                # Try to find the closest link element
                parent = match.parent
                while parent and parent.name != 'html':
                    # Look for article links in various LinkedIn post structures
                    post_links = parent.find_all('a', href=re.compile(r'/(posts/|pulse/)', re.IGNORECASE))
                    for link in post_links:
                        href = link.get('href', '')
                        if href and '/posts/' in href:  # Focus on actual posts
                            if not href.startswith('http'):
                                href = 'https://www.linkedin.com' + href
                            found_links.append(href)
                            print(f"Found AI news post link: {href}")
                    parent = parent.parent
        
        # Alternative approach: Look for activity/posts section
        if not found_links:
            print("No direct links found, trying activity section...")
            activity_sections = soup.find_all(['section', 'div'], class_=re.compile(r'activity|posts|updates', re.IGNORECASE))
            for section in activity_sections:
                post_links = section.find_all('a', href=re.compile(r'/posts/'))
                for link in post_links[:3]:  # Check first 3 posts
                    href = link.get('href', '')
                    if href:
                        if not href.startswith('http'):
                            href = 'https://www.linkedin.com' + href
                        found_links.append(href)
                        print(f"Found activity post link: {href}")
        
        # Remove duplicates and return the most recent
        if found_links:
            unique_links = list(dict.fromkeys(found_links))  # Remove duplicates while preserving order
            print(f"Found {len(unique_links)} unique post links")
            return unique_links[0]  # Return the first (most recent)
        else:
            print("No AI news posts found - LinkedIn may be blocking automated access")
            return None
        
    except Exception as e:
        print(f"Error finding LinkedIn post: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        pass

def scrape_article_links_improved(article_url):
    """
    Improved article link scraping with better filtering and error handling.
    
    Args:
        article_url (str): URL of the AI news article
        
    Returns:
        list: List of dictionaries containing title and link
    """
    page = None
    try:
        print(f"Scraping article links from: {article_url}")
        safari_user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
        with PlaywrightBrowser(headless=True, user_agent=safari_user_agent) as page:
            for attempt in range(3):
                try:
                    page.goto(article_url, timeout=30_000, wait_until="domcontentloaded")
                    time.sleep(10)
                    html_content = page.content()
                    soup = BeautifulSoup(html_content, 'html.parser')
                    if "sign in" in html_content.lower() or "join linkedin" in html_content.lower():
                        print(f"Attempt {attempt + 1}: LinkedIn blocking access, retrying...")
                        time.sleep(5)
                        continue
                    break
                except Exception as e:
                    print(f"Attempt {attempt + 1} failed: {e}")
                    if attempt == 2:
                        raise
                    time.sleep(5)
        
        article_links = []
        
        # Look for article content with improved selectors
        content_selectors = [
            '[data-test-id*="post-content"]',
            '[class*="feed-shared-update-v2__description"]',
            '[class*="break-words"]',
            '[class*="feed-shared-text"]',
            'article',
            '[role="article"]'
        ]
        
        content_area = None
        for selector in content_selectors:
            content_area = soup.select_one(selector)
            if content_area:
                print(f"Found content area with selector: {selector}")
                break
        
        if not content_area:
            print("No specific content area found, using entire body")
            content_area = soup.find('body')
        
        if content_area:
            # Find all links in the content area
            links = content_area.find_all('a', href=True)
            
            for link in links:
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                # Improved filtering for quality articles
                if (href and text and 
                    len(text) > 15 and  # Longer titles are usually better
                    not any(skip in href.lower() for skip in [
                        'linkedin.com', 'javascript:', 'mailto:', '#', 
                        'facebook.com', 'twitter.com', 'instagram.com'
                    ]) and
                    any(domain in href.lower() for domain in [
                        '.com', '.org', '.net', '.ai', '.co', '.io', '.tech'
                    ]) and
                    # Filter for AI/tech related content
                    any(keyword in text.lower() for keyword in [
                        'ai', 'artificial intelligence', 'machine learning', 'ml',
                        'neural', 'algorithm', 'data', 'tech', 'automation',
                        'robot', 'deep learning', 'nlp', 'computer', 'digital'
                    ])):
                    
                    # Clean up the URL
                    if href.startswith('//'):
                        href = 'https:' + href
                    elif not href.startswith('http'):
                        href = 'https://' + href.lstrip('/')
                    
                    article_links.append({
                        'title': text.strip(),
                        'url': href.strip()
                    })
        
        # Remove duplicates and sort by title length (longer titles usually better)
        seen_urls = set()
        unique_links = []
        for link in sorted(article_links, key=lambda x: len(x['title']), reverse=True):
            if link['url'] not in seen_urls:
                seen_urls.add(link['url'])
                unique_links.append(link)
        
        print(f"Found {len(unique_links)} unique article links")
        return unique_links[:20]  # Limit to top 20 articles
        
    except Exception as e:
        print(f"Error scraping article links: {e}")
        import traceback
        traceback.print_exc()
        return []
    finally:
        pass

def extract_article_metadata(url):
    """
    Extract metadata from an article URL.
    
    Args:
        url (str): Article URL
        
    Returns:
        dict: Article metadata including title, description, date, guid
    """
    page = None
    try:
        print(f"Extracting metadata from: {url}")
        safari_user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
        with PlaywrightBrowser(headless=True, user_agent=safari_user_agent) as page:
            page.goto(url, timeout=15_000, wait_until="domcontentloaded")
            time.sleep(3)
            html_content = page.content()
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
        pass

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
    article_links = scrape_article_links_improved(latest_post_url)
    
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
    Runs both GAI Insights and EEI LinkedIn scraping.
    """
    # Part 1: Original GAI Insights scraping
    print("=" * 60)
    print("PART 1: GAI INSIGHTS SCRAPING")
    print("=" * 60)
    
    url = "https://gaiinsights.com/ratings"
    table_id = "newsTable"
    
    print("Starting GAI Insights table scraping and RSS generation...")
    
    # Scrape table data
    current_data = scrape_table_data(url, table_id)
    
    if not current_data:
        print("No data found or error occurred during GAI scraping")
        # Still generate an empty RSS feed to maintain consistency
        generate_rss_feed([], "GAI Insights Ratings", "No data available at this time")
    else:
        # Load previous data for comparison
        previous_data = load_previous_data()
        
        # Check if data has changed
        if current_data == previous_data.get('data', []):
            print("No changes detected in GAI table data")
        else:
            print("Changes detected in GAI table data")
        
        # Save current data
        save_current_data({'data': current_data, 'timestamp': datetime.now(timezone.utc).isoformat()})
        
        # Generate RSS feed
        generate_rss_feed(current_data)
        
        print("GAI Insights process completed successfully!")
    
    # Part 2: EEI LinkedIn scraping
    print("\n" + "=" * 60)
    print("PART 2: EEI LINKEDIN SCRAPING")
    print("=" * 60)
    
    try:
        scrape_eei_and_generate_feed()
    except Exception as e:
        print(f"Error in EEI LinkedIn scraping: {e}")
        import traceback
        traceback.print_exc()
        # Generate empty RSS feed as fallback
        generate_eei_rss_feed([], "EEI AI News", "Error occurred during LinkedIn scraping")
    
    print("\n" + "=" * 60)
    print("ALL PROCESSES COMPLETED")
    print("=" * 60)

if __name__ == "__main__":
    main()
