# RSS Feed Scraper - Configuration

# URLs and Targets
GAI_INSIGHTS_URL = "https://gaiinsights.com/ratings"
GAI_TABLE_ID = "newsTable"

# RSS Feed Settings
RSS_FEED_FILES = {
    "gai": "ai_rss_feed.xml",
    "gai_archive": "ai_rss_feed_archive.xml"
}

RSS_METADATA = {
    "gai": {
        "title": "Ted Tschopp's AI News",
        "description": "Latest AI News and Ratings from Ted Tschopp",
        "link": "https://rss.tedt.org/"
    }
}

# Scraping Settings
SCRAPING_CONFIG = {
    "page_load_timeout": 30,
    "dynamic_content_wait": 10,
    "max_articles_per_feed": 512,
    "retry_attempts": 3,
    "retry_delay": 5
}

# Browser Settings
BROWSER_CONFIG = {
    "headless": True,
    "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "window_size": "1920,1080"
}

# Rating Tags for GAI Insights
RATING_TAGS = {
    "essential": " [ ! ]",
    "important": " [ * ]",
    "optional": " [ ~ ]"
}

# (Former LinkedIn patterns removed)

# Content Filtering
CONTENT_FILTERS = {
    "excluded_domains": [
        "facebook.com", "twitter.com", "instagram.com"
    ],
    "required_domains": [
        ".com", ".org", ".net", ".ai", ".co", ".io", ".tech"
    ],
    "ai_keywords": [
        "ai", "artificial intelligence", "machine learning", "ml",
        "neural", "algorithm", "data", "tech", "automation",
        "robot", "deep learning", "nlp", "computer", "digital"
    ],
    "min_title_length": 15,
    "max_description_length": 1024
}
