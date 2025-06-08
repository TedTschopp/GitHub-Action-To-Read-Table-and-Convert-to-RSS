# GitHub Pages Jekyll Site

This directory contains the Jekyll site configuration for displaying RSS feeds at https://rss.tedt.org.

## Local Development

To run the Jekyll site locally:

1. Install Ruby and Bundler
2. Run `bundle install` to install dependencies
3. Run `bundle exec jekyll serve` to start the development server
4. Visit `http://localhost:4000` to view the site

## Site Structure

- `_config.yml` - Jekyll configuration
- `_layouts/default.html` - Main layout template
- `index.html` - Homepage displaying RSS feeds and status
- `about.md` - About page with site information
- `Gemfile` - Ruby dependencies
- `assets/` - Static assets (images, CSS, JS)

## Features

- **RSS Feed Display**: Shows preview of latest entries from each RSS feed
- **Health Monitoring**: Displays real-time status of each feed
- **Responsive Design**: Mobile-friendly Bootstrap-based layout
- **SEO Optimized**: Proper meta tags and structured data
- **Fast Loading**: Minimal dependencies and optimized assets

## Deployment

The site is automatically deployed via GitHub Actions when changes are pushed to the main branch. The workflow:

1. Runs the RSS scraping and monitoring scripts
2. Builds the Jekyll site
3. Deploys to GitHub Pages

## RSS Feeds

The site displays the following RSS feeds:

- **GAI Insights**: AI and technology insights from scraped sources
- **LinkedIn AI News**: AI news from LinkedIn (when working properly)

Each feed includes:
- Live preview of latest entries
- Direct RSS feed links
- Health status monitoring
- Entry count and last update information
