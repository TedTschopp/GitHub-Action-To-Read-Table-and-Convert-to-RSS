---
layout: default
title: "About RSS Feed Hub"
---

<div class="row">
    <div class="col-md-8">
        <h1>About RSS Feed Hub</h1>
        
        <p>Welcome to RSS Feed Hub, your centralized source for curated AI and technology news feeds. This site automatically aggregates and monitors RSS feeds from various sources to keep you updated with the latest developments in artificial intelligence and technology.</p>
        
        <h2>Available Feeds</h2>
        
        {% for feed in site.rss_feeds %}
        <div class="card mb-3">
            <div class="card-body">
                <h5 class="card-title">
                    <a href="{{ feed.url }}">{{ feed.name }}</a>
                    <a href="{{ feed.url }}" class="btn btn-sm btn-outline-success ms-2">
                        <i class="fas fa-rss"></i> RSS
                    </a>
                </h5>
                <p class="card-text">{{ feed.description }}</p>
            </div>
        </div>
        {% endfor %}
        
        <h2>How It Works</h2>
        
        <p>Our system uses automated web scraping and monitoring to:</p>
        
        <ul>
            <li><strong>Scrape Content:</strong> Automatically extract articles and news from target websites</li>
            <li><strong>Generate RSS:</strong> Convert scraped content into standard RSS feed format</li>
            <li><strong>Monitor Health:</strong> Continuously check feed status and entry counts</li>
            <li><strong>Update Regularly:</strong> Refresh content on a scheduled basis via GitHub Actions</li>
        </ul>
        
        <h2>Priority Badges</h2>
        
        <p>RSS feed entries can include priority indicators in their titles, which are automatically converted to visual badges:</p>
        
        <ul>
            <li><strong>[ ! ]</strong> → <span class="badge bg-danger">Essential</span> - Critical or urgent content</li>
            <li><strong>[ * ]</strong> → <span class="badge bg-warning text-dark">Important</span> - High-priority content</li>
            <li><strong>[ ~ ]</strong> → <span class="badge bg-secondary">Optional</span> - Supplementary or nice-to-know content</li>
        </ul>
        
        <p>These badges help you quickly identify the importance level of each RSS entry on the homepage.</p>
        
        <h2>Smart Preview Display</h2>
        
        <p>The homepage RSS previews use intelligent filtering to show the most relevant content:</p>
        
        <ul>
            <li><strong>Recent Content Priority:</strong> Always shows items from the last 7 days when available</li>
            <li><strong>Minimum Guarantee:</strong> Ensures at least the configured preview limit (default: 5 items) are shown</li>
            <li><strong>Adaptive Display:</strong> Shows whichever is larger - recent items (7 days) or the preview limit</li>
        </ul>
        
        <p>This ensures you see fresh, timely content while maintaining a minimum number of items for context.</p>
        
        <h2>Feed Status Monitoring</h2>
        
        <p>Each feed is continuously monitored for:</p>
        
        <ul>
            <li>Entry count and freshness</li>
            <li>Last update timestamp</li>
            <li>Error detection and reporting</li>
            <li>Feed validity and accessibility</li>
        </ul>
        
        <h2>Technical Details</h2>
        
        <p>This RSS hub is powered by:</p>
        
        <ul>
            <li><strong>Python:</strong> Web scraping with Beautiful Soup and Selenium</li>
            <li><strong>GitHub Actions:</strong> Automated workflow execution</li>
            <li><strong>Jekyll:</strong> Static site generation</li>
            <li><strong>RSS:</strong> Standard syndication format</li>
        </ul>
        
        <div class="alert alert-info mt-4">
            <h5><i class="fas fa-info-circle"></i> Note</h5>
            <p class="mb-0">RSS feeds are updated automatically. If you notice any issues with feed content or availability, please check the <a href="{{ site.baseurl }}/">main page</a> for current status information.</p>
        </div>
    </div>
    
    <div class="col-md-4">
        <div class="card">
            <div class="card-header">
                <h5><i class="fas fa-chart-line"></i> Quick Stats</h5>
            </div>
            <div class="card-body">
                <div id="quick-stats">
                    Loading stats...
                </div>
            </div>
        </div>
        
        <div class="card mt-4">
            <div class="card-header">
                <h5><i class="fas fa-link"></i> Useful Links</h5>
            </div>
            <div class="card-body">
                <ul class="list-unstyled">
                    {% if site.github_url %}
                    <li><a href="{{ site.github_url }}" target="_blank"><i class="fab fa-github"></i> Source Code</a></li>
                    {% endif %}
                    <li><a href="{{ site.baseurl }}/rss_status.json"><i class="fas fa-file-code"></i> Status JSON</a></li>
                    {% for feed in site.rss_feeds %}
                    <li><a href="{{ feed.url }}"><i class="fas fa-rss"></i> {{ feed.name }}</a></li>
                    {% endfor %}
                </ul>
            </div>
        </div>
    </div>
</div>

<script>
document.addEventListener('DOMContentLoaded', function() {
    // Load quick stats
    fetch('/rss_status.json')
        .then(response => response.json())
        .then(data => {
            let totalEntries = 0;
            let healthyFeeds = 0;
            let totalFeeds = 0;
            
            if (data.feeds) {
                Object.values(data.feeds).forEach(feed => {
                    totalFeeds++;
                    if (feed.status === 'healthy') {
                        healthyFeeds++;
                    }
                    totalEntries += feed.entry_count || 0;
                });
            }
            
            const statsHtml = `
                <div class="row text-center">
                    <div class="col-6">
                        <h3 class="text-primary">${totalFeeds}</h3>
                        <small>Total Feeds</small>
                    </div>
                    <div class="col-6">
                        <h3 class="text-success">${healthyFeeds}</h3>
                        <small>Healthy Feeds</small>
                    </div>
                    <div class="col-12 mt-3">
                        <h3 class="text-info">${totalEntries}</h3>
                        <small>Total Entries</small>
                    </div>
                </div>
                <hr>
                <small class="text-muted">
                    Last updated: ${data.timestamp ? new Date(data.timestamp).toLocaleString() : 'Unknown'}
                </small>
            `;
            
            document.getElementById('quick-stats').innerHTML = statsHtml;
        })
        .catch(error => {
            console.error('Error loading stats:', error);
            document.getElementById('quick-stats').innerHTML = 
                '<div class="text-muted">Unable to load statistics</div>';
        });
});
</script>
