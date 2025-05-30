# GitHub Action: Table Scraper to RSS Feed

This GitHub Action scrapes table data from websites and converts it to an RSS feed that gets saved to your repository.

## Features

- 🕐 **Automated Scheduling**: Runs every hour to check for new data
- 🔄 **Manual Triggering**: Can be triggered manually via GitHub Actions UI
- 📊 **Table Scraping**: Extracts data from table with ID "newsTable"
- 📡 **RSS Generation**: Creates a properly formatted RSS feed
- 💾 **Change Detection**: Only commits when data actually changes
- 🔗 **Link Preservation**: Maintains any links found in table cells

## Setup

1. **Enable GitHub Actions**: Make sure GitHub Actions are enabled for your repository
2. **Set Permissions**: The workflow has `contents: write` permission to commit the RSS feed back to the repo
3. **Files Created**:
   - `.github/workflows/scrape-and-generate-rss.yml` - The GitHub Action workflow
   - `scrape_to_rss.py` - Python script that does the scraping and RSS generation
   - `requirements.txt` - Python dependencies
   - `ai_rss_feed.xml` - Generated RSS feed (created after first run)
   - `previous_data.json` - Stores previous data for change detection

## How It Works

1. **Scraping**: The script fetches the webpage and extracts all data from the table with ID "newsTable"
2. **Data Processing**: Extracts text content and any links from each table cell
3. **Change Detection**: Compares current data with previously saved data
4. **RSS Generation**: Creates RSS entries from table rows, using first 3 columns for titles
5. **Repository Update**: Commits the updated RSS feed if changes are detected

## Customization

You can customize the script by modifying these variables in `scrape_to_rss.py`:

- `url`: Change the target URL
- `table_id`: Change the table ID to scrape
- `feed_title`: Customize the RSS feed title
- `feed_description`: Customize the RSS feed description

## Schedule

The action runs:
- **Automatically**: Every hour at minute 0 (configurable in the workflow file)
- **Manually**: Via the "Actions" tab in your GitHub repository

## Generated RSS Feed

The RSS feed will be available at:
`https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/ai_rss_feed.xml`

## Troubleshooting

- Check the Actions tab for any errors
- The script includes detailed logging for debugging
- If the table structure changes, you may need to update the scraping logic
- Make sure the repository has write permissions for the action

## Dependencies

- `requests`: For HTTP requests
- `beautifulsoup4`: For HTML parsing
- `lxml`: XML parser for BeautifulSoup
- `feedgen`: For RSS feed generation
