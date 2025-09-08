# GitHub Action: Table / Feed Aggregator to RSS

This project scrapes a dynamic table (GAI Insights) and also aggregates multiple external RSS feeds into unified local RSS outputs (with retention + archives) automatically via GitHub Actions.

## Features (Current)

- ⏱️ Scheduled (every 8 hours) + manual dispatch
- 🧮 Table scraping (Playwright) for `newsTable` (GAI Insights)
- � Primary AI feed: `ai_rss_feed.xml`
- 🗂️ Automatic 60-day retention + `ai_rss_feed_archive.xml`
- 🌐 Multi-source external aggregation: `aggregated_external.xml`
- 🗄️ Aggregated archive: `aggregated_external_archive.xml`
- � Change detection with JSON snapshot
- 🛡️ Robust error handling & retries
- � Health monitoring (`monitor.py`) writing `rss_status.json`

## Setup

1. **Enable GitHub Actions**: Make sure GitHub Actions are enabled for your repository
2. **Set Permissions**: The workflow has `contents: write` permission to commit the RSS feed back to the repo
3. **Files of Interest**:
   - `enhanced_scraper.py` (primary orchestrator: scraping + aggregation + retention)
   - `monitor.py` (feed health & summary)
   - `config.py` (constants & defaults)
   - `_config.yml` (Jekyll + aggregation settings)
   - `ai_rss_feed.xml` / `ai_rss_feed_archive.xml`
   - `aggregated_external.xml` / `aggregated_external_archive.xml`
   - `previous_data.json` (change tracking)

## How It Works

1. **Scraping**: The script fetches the webpage and extracts all data from the table with ID "newsTable"
2. **Data Processing**: Extracts text content and any links from each table cell
3. **Change Detection**: Compares current data with previously saved data
4. **RSS Generation**: Creates RSS entries from table rows, using first 3 columns for titles
5. **Repository Update**: Commits the updated RSS feed if changes are detected

## Customization

Primary customization via `_config.yml` (aggregation) & `config.py` (scraping/filters).

Example aggregation block:

```yaml
aggregated_feeds:
   enabled: true
   output: "/aggregated_external.xml"
   max_items: 150
   retention_days: 60
   source_attribution: title  # or description / none
   sources:
      - "https://feeds.arstechnica.com/arstechnica/technology-lab"
      - "https://www.infoworld.com/index.rss"
```

## Schedule

The action runs:
- **Automatically**: Every hour at minute 0 (configurable in the workflow file)
- **Manually**: Via the "Actions" tab in your GitHub repository

## Generated RSS Feeds

Primary AI Feed: `/ai_rss_feed.xml` (+ archive `/ai_rss_feed_archive.xml`)

Aggregated External Feed: `/aggregated_external.xml` (+ archive `/aggregated_external_archive.xml`)

## Troubleshooting

- Check the Actions tab for any errors
- The script includes detailed logging for debugging
- If the table structure changes, you may need to update the scraping logic
- Make sure the repository has write permissions for the action

## Dependencies

- `requests`: For HTTP requests
- `beautifulsoup4`: For HTML parsing
- `PyYAML`: Parse Jekyll `_config.yml` aggregation settings
- `feedgen`: For RSS feed generation
