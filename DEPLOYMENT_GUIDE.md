# Jekyll RSS Feed Hub Deployment Guide

This guide covers the Jekyll site setup and deployment for the RSS Feed Hub at https://rss.tedt.org.

## 🚀 Deployment Status

The Jekyll site is automatically deployed via GitHub Actions to GitHub Pages. The workflow:

1. **RSS Scraping**: Runs the enhanced scraper to update feeds
2. **Health Monitoring**: Checks feed status and generates reports  
3. **Jekyll Build**: Builds the static site with latest RSS data
4. **GitHub Pages Deploy**: Deploys to https://rss.tedt.org

## 📁 Site Structure

```
├── _config.yml           # Jekyll configuration
├── _layouts/
│   └── default.html      # Main site template
├── index.html            # Homepage with RSS previews
├── feeds.html            # RSS feeds listing page
├── about.md              # About page
├── 404.html              # Error page
├── robots.txt            # SEO robots file
├── sitemap.xml           # XML sitemap
├── Gemfile               # Ruby dependencies
└── assets/               # Static assets
```

## 🎨 Features

### RSS Feed Display
- **Live Previews**: Shows latest 5 entries from each feed
- **Health Status**: Real-time monitoring with status badges
- **Direct Links**: Easy access to raw RSS feeds
- **Mobile Responsive**: Bootstrap-based responsive design

### Feed Monitoring
- **Entry Counts**: Shows number of articles in each feed
- **Last Updated**: Displays when feeds were last refreshed
- **Error Detection**: Alerts when feeds are unhealthy
- **JSON API**: Exposes feed status at `/rss_status.json`

### SEO & Performance
- **Fast Loading**: Minimal dependencies, CDN assets
- **SEO Optimized**: Proper meta tags, sitemap, robots.txt
- **RSS Autodiscovery**: Browser RSS detection
- **Social Meta**: Open Graph and Twitter Card support

## 🔧 Configuration

### Site Settings (`_config.yml`)
```yaml
# Basic site info
title: RSS Feed Hub
url: "https://rss.tedt.org"
description: "Curated RSS feeds for AI Insights and Technology News"

# RSS feeds configuration
rss_feeds:
  - name: "GAI Insights"
    url: "/ai_rss_feed.xml"
    description: "Latest AI and technology insights"
  # LinkedIn AI News feed removed (deprecated)
```

### GitHub Actions Workflow
The deployment is triggered by:
- **Schedule**: Every 8 hours (for RSS updates)
- **Manual**: Via workflow_dispatch
- **Push**: When Jekyll files are modified

## 📊 Monitoring

### Feed Status API
Get real-time feed status: `GET /rss_status.json`

```json
{
  "timestamp": "2024-01-01T12:00:00Z",
  "feeds": {
    "GAI Insights": {
      "status": "healthy",
      "entry_count": 50,
      "last_updated": "2024-01-01T11:30:00Z"
  }
  }
}
```

### GitHub Actions Summary
Each workflow run generates a summary showing:
- RSS feed update status
- Jekyll build and deployment status
- Direct links to deployed site
- Timestamps and change detection

## 🐛 Troubleshooting

### Common Issues

**1. Jekyll Build Fails**
- Check `Gemfile` dependencies
- Verify Ruby version compatibility
- Review Jekyll liquid syntax in templates

**2. RSS Feeds Not Loading**
- Check if RSS XML files exist in repository
- Verify feed URLs in `_config.yml`
- Test feed validity with RSS validators

**3. JavaScript Errors**
- Check browser console for CORS issues
- Verify RSS feed accessibility
- Test with different browsers

**4. Deployment Fails**
- Check GitHub Pages settings
- Verify repository permissions
- Review workflow logs for errors

### Local Development

To run the site locally:

```bash
# Install dependencies
bundle install

# Start Jekyll server
bundle exec jekyll serve

# View at http://localhost:4000
```

### Manual Deployment

If needed, manually deploy:

```bash
# Build site
bundle exec jekyll build

# Deploy _site/ contents to web server
```

## 🔮 Future Enhancements

Planned improvements:
- [ ] Custom Jekyll theme based on Jasper
- [ ] Advanced RSS feed categorization
- [ ] Email/Slack notifications for feed failures
- [ ] Feed analytics and metrics
- [ ] Content search functionality
- [ ] Mobile app integration

## 📞 Support

For issues or questions:
- Check GitHub Actions workflow logs
- Review Jekyll build output
- Test RSS feeds individually
- Verify GitHub Pages configuration

The site automatically updates with fresh RSS content every 8 hours, ensuring visitors always see the latest AI and technology news.
