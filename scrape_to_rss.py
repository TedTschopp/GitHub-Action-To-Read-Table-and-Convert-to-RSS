#!/usr/bin/env python3
"""
GitHub Action script to scrape table data from gaiinsights.com/ratings
and generate an RSS feed.
"""

import requests
import json
import hashlib
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
import os
import sys

def scrape_table_data(url, table_id):
    """
    Scrape table data from the specified URL and table ID.
    
    Args:
        url (str): The URL to scrape
        table_id (str): The ID of the table to scrape
        
    Returns:
        list: List of dictionaries containing table row data
    """
    try:
        # Set headers to mimic a real browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        print(f"Fetching data from: {url}")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find the table with the specified ID
        table = soup.find('table', id=table_id)
        if not table:
            print(f"Error: Table with ID '{table_id}' not found on the page")
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
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL: {e}")
        return []
    except Exception as e:
        print(f"Error parsing table data: {e}")
        return []

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

def generate_rss_feed(table_data, feed_title="GAI Insights Ratings", feed_description="Latest ratings from GAI Insights"):
    """
    Generate RSS feed from table data.
    
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
            
            # Create a unique ID for each entry based on content
            content_str = json.dumps(row_data, sort_keys=True)
            entry_id = hashlib.md5(content_str.encode()).hexdigest()
            
            # Create title from first few columns
            title_parts = []
            for key, value in list(row_data.items())[:3]:  # Use first 3 columns for title
                if value['text']:
                    title_parts.append(f"{key}: {value['text']}")
            
            title = " | ".join(title_parts) if title_parts else f"Entry {i+1}"
            
            # Create description from all data
            description_parts = []
            for key, value in row_data.items():
                if value['text']:
                    desc_part = f"<strong>{key}:</strong> {value['text']}"
                    if value['links']:
                        links_html = " | ".join([f'<a href="{link}">{link}</a>' for link in value['links']])
                        desc_part += f" (Links: {links_html})"
                    description_parts.append(desc_part)
            
            description = "<br/><br/>".join(description_parts)
            
            fe.id(f"https://gaiinsights.com/ratings#{entry_id}")
            fe.title(title)
            fe.description(description)
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
