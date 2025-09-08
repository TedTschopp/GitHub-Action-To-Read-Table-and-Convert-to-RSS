# GitHub Action: Table Scraper to RSS Feed - Enhanced

A sophisticated GitHub Action that scrapes table data from websites to generate an AI news RSS feed automatically.

## 🚀 New Features (v2.0)

- **🔄 Automated RSS Feed**: GAI Insights table scraping
- **📊 Health Monitoring**: Automated RSS feed health checks and status reports
- **⚙️ Configuration Management**: Centralized configuration for easy customization
- **🛡️ Enhanced Error Handling**: Robust error handling with retry mechanisms
- **📈 Better Change Detection**: Intelligent change detection to avoid unnecessary updates
- **📝 Structured Logging**: Comprehensive logging for debugging and monitoring
- **🎯 Smart Content Filtering**: AI-focused content filtering and normalization

## 📁 Project Structure

```
├── scrape_to_rss.py          # Original scraper (legacy)
├── enhanced_scraper.py       # New enhanced scraper with better architecture
├── monitor.py                # RSS feed health monitoring
├── config.py                 # Centralized configuration
├── requirements.txt          # Python dependencies
├── .github/workflows/        # GitHub Actions workflows
│   └── scrape-and-generate-rss.yml
├── ai_rss_feed.xml          # GAI Insights RSS feed
└── rss_status.json          # Health monitoring report
```

## 📊 RSS Feeds Generated

### 1. GAI Insights RSS Feed (`ai_rss_feed.xml`)
- Scrapes the ratings table from [gaiinsights.com/ratings](https://gaiinsights.com/ratings)
- Updates every 8 hours
- Includes rating tags: Essential [!], Important [*], Optional [~]

<!-- Former secondary feed removed to simplify scope -->

## 🔧 Configuration

All settings are centralized in `config.py`:

```python
# URL target
GAI_INSIGHTS_URL = "https://gaiinsights.com/ratings"

# Scraping settings
SCRAPING_CONFIG = {
    "page_load_timeout": 30,
    "dynamic_content_wait": 10,
    "max_articles_per_feed": 50
}

# Content filtering
CONTENT_FILTERS = {
    "ai_keywords": ["ai", "artificial intelligence", "machine learning"],
    "min_title_length": 15
}
```

## 📈 Health Monitoring

The project includes comprehensive health monitoring:

- **Automatic Checks**: Validates RSS feed structure and content
- **Status Reports**: Generates JSON status reports with detailed metrics
- **GitHub Actions Summary**: Creates visual status summaries in GitHub Actions
- **Error Tracking**: Tracks and reports errors with detailed diagnostics

## 🎯 Advanced Features

### Smart Content Detection
- Intelligent column identification for flexible table structures
- Duplicate detection and removal

### Robust Error Handling
- Retry mechanisms for failed requests
- Graceful degradation when services are unavailable
- Comprehensive error logging and reporting

### Performance Optimization
- Efficient change detection to avoid unnecessary processing
- Configurable timeouts and retry policies
- Resource cleanup and memory management

## 🚀 Getting Started

### Local Development

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the Enhanced Scraper**:
   ```bash
   python enhanced_scraper.py
   ```

3. **Run Health Monitoring**:
   ```bash
   python monitor.py
   ```

### GitHub Actions Setup

The workflow runs automatically every 8 hours and can be triggered manually:

1. **Automatic**: Every 8 hours at minute 0
2. **Manual**: Via GitHub Actions UI (`workflow_dispatch`)

## 📊 Monitoring and Alerts

### RSS Feed Status Report

The monitoring system generates detailed reports including:

- Feed existence and validity
- Entry counts and content quality
- File sizes and last update times
- Error tracking and diagnostics

### GitHub Actions Integration

- Visual status summaries in GitHub Actions
- Automated commit and push of updated feeds
- Error notifications and status badges

## 🔄 Workflow Process

1. **Scraping Phase**:
   - Scrape GAI Insights table data
   - Extract table rows and transform into RSS entries

2. **Processing Phase**:
   - Generate RSS feeds with proper formatting
   - Apply content filtering and validation
   - Detect changes from previous runs

3. **Monitoring Phase**:
   - Validate RSS feed health
   - Generate status reports
   - Create GitHub Actions summaries

4. **Publishing Phase**:
   - Commit updated feeds to repository
   - Update status reports
   - Trigger any configured notifications

## 🛠️ Customization

### Adding New Data Sources

1. Create a new scraper class in `enhanced_scraper.py`
2. Add configuration in `config.py`
3. Update the RSS generation logic
4. Add monitoring for the new feed

### Modifying Content Filters

Edit the `CONTENT_FILTERS` in `config.py`:

```python
CONTENT_FILTERS = {
    "ai_keywords": ["your", "custom", "keywords"],
    "excluded_domains": ["spam.com"],
    "min_title_length": 10
}
```

### Adjusting Scraping Behavior

Modify `SCRAPING_CONFIG` in `config.py`:

```python
SCRAPING_CONFIG = {
    "page_load_timeout": 45,
    "retry_attempts": 5,
    "max_articles_per_feed": 100
}
```

## 📱 Accessing RSS Feeds

Your RSS feeds will be available at:

- **GAI Insights**: `https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/ai_rss_feed.xml`

## 🐛 Troubleshooting

### Common Issues

1. **Empty RSS Feed**: No content found
   - Check status report in `rss_status.json`
   - Verify source website structure hasn't changed
   - Review error logs in GitHub Actions

2. **Timeout Errors**: Slow page loading
   - Increase timeout values in `config.py`
   - Check GitHub Actions runner performance
   - Consider reducing content processing

### Debug Information

Enable debug mode by setting environment variable:
```bash
export DEBUG=true
python enhanced_scraper.py
```

This generates debug HTML files for inspection.

## 📈 Performance Metrics

The system tracks various performance metrics:

- Scraping success rates
- Feed generation times
- Content quality scores
- Error frequencies

## 🔮 Future Enhancements

- [ ] Multi-source RSS aggregation
- [ ] Advanced content analysis and tagging
- [ ] Real-time notifications for high-priority content
- [ ] Machine learning-based content recommendation
- [ ] API endpoints for programmatic access
- [ ] Advanced analytics and reporting
- [ ] Integration with additional social platforms

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
