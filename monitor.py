#!/usr/bin/env python3
"""
Monitoring script to check RSS feed health and send notifications.
"""

import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

def check_rss_health():
    """
    Check the health of generated RSS feeds and return status report.
    
    Returns:
        dict: Status report of RSS feeds
    """
    status = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'feeds': {},
        'overall_status': 'healthy'
    }
    
    # EEI feed disabled (LinkedIn source discontinued). Retain code but skip monitoring.
    rss_files = ['ai_rss_feed.xml', 'ai_rss_feed_archive.xml', 'aggregated_external.xml', 'aggregated_external_archive.xml']
    
    for rss_file in rss_files:
        feed_status = {
            'exists': False,
            'valid_xml': False,
            'entry_count': 0,
            'last_updated': None,
            'size_bytes': 0,
            'errors': []
        }
        
        try:
            if Path(rss_file).exists():
                feed_status['exists'] = True
                feed_status['size_bytes'] = Path(rss_file).stat().st_size
                
                # Parse XML to check validity and count entries
                try:
                    tree = ET.parse(rss_file)
                    root = tree.getroot()
                    feed_status['valid_xml'] = True
                    
                    # Count items
                    items = root.findall('.//item')
                    feed_status['entry_count'] = len(items)
                    
                    # Get last build date
                    last_build = root.find('.//lastBuildDate')
                    if last_build is not None:
                        feed_status['last_updated'] = last_build.text
                    
                    # Check for minimum entries
                    if feed_status['entry_count'] == 0:
                        feed_status['errors'].append('No entries in RSS feed')
                        status['overall_status'] = 'warning'
                    elif feed_status['entry_count'] < 5:
                        feed_status['errors'].append(f'Low entry count: {feed_status["entry_count"]}')
                        status['overall_status'] = 'warning'
                        
                except ET.ParseError as e:
                    feed_status['errors'].append(f'Invalid XML: {str(e)}')
                    status['overall_status'] = 'error'
                    
            else:
                # Treat missing archives as warning, primary feeds as error
                if rss_file.endswith('_archive.xml'):
                    feed_status['errors'].append('Archive not yet created')
                    if status['overall_status'] != 'error':
                        status['overall_status'] = 'warning'
                else:
                    feed_status['errors'].append('RSS file does not exist')
                    status['overall_status'] = 'error'
                
        except Exception as e:
            feed_status['errors'].append(f'Unexpected error: {str(e)}')
            status['overall_status'] = 'error'
        
        status['feeds'][rss_file] = feed_status
    
    return status

def save_status_report(status):
    """
    Save status report to JSON file.
    
    Args:
        status (dict): Status report dictionary
    """
    try:
        with open('rss_status.json', 'w') as f:
            json.dump(status, f, indent=2)
        print("Status report saved to rss_status.json")
    except Exception as e:
        print(f"Error saving status report: {e}")

def print_status_summary(status):
    """
    Print a human-readable status summary.
    
    Args:
        status (dict): Status report dictionary
    """
    print(f"\n{'='*50}")
    print(f"RSS FEED HEALTH REPORT")
    print(f"{'='*50}")
    print(f"Timestamp: {status['timestamp']}")
    print(f"Overall Status: {status['overall_status'].upper()}")
    print()
    
    for feed_name, feed_status in status['feeds'].items():
        print(f"📄 {feed_name}")
        print(f"   ✅ Exists: {feed_status['exists']}")
        print(f"   📊 Valid XML: {feed_status['valid_xml']}")
        print(f"   📈 Entries: {feed_status['entry_count']}")
        print(f"   📏 Size: {feed_status['size_bytes']} bytes")
        print(f"   🕐 Last Updated: {feed_status['last_updated']}")
        
        if feed_status['errors']:
            print(f"   ⚠️  Errors:")
            for error in feed_status['errors']:
                print(f"      - {error}")
        print()

def create_github_action_summary(status):
    """
    Create GitHub Action summary output.
    
    Args:
        status (dict): Status report dictionary
    """
    if 'GITHUB_STEP_SUMMARY' in os.environ:
        summary_file = os.environ['GITHUB_STEP_SUMMARY']
        
        with open(summary_file, 'w') as f:
            f.write("# RSS Feed Health Report\n\n")
            f.write(f"**Overall Status:** {status['overall_status'].upper()}\n")
            f.write(f"**Timestamp:** {status['timestamp']}\n\n")
            
            f.write("## Feed Status\n\n")
            f.write("| Feed | Exists | Valid XML | Entries | Size | Errors |\n")
            f.write("|------|--------|-----------|---------|------|--------|\n")
            
            for feed_name, feed_status in status['feeds'].items():
                exists_icon = "✅" if feed_status['exists'] else "❌"
                valid_icon = "✅" if feed_status['valid_xml'] else "❌"
                error_count = len(feed_status['errors'])
                error_text = f"{error_count} errors" if error_count > 0 else "None"
                
                f.write(f"| {feed_name} | {exists_icon} | {valid_icon} | {feed_status['entry_count']} | {feed_status['size_bytes']} bytes | {error_text} |\n")
            
            # Add error details if any
            has_errors = any(feed['errors'] for feed in status['feeds'].values())
            if has_errors:
                f.write("\n## Error Details\n\n")
                for feed_name, feed_status in status['feeds'].items():
                    if feed_status['errors']:
                        f.write(f"### {feed_name}\n")
                        for error in feed_status['errors']:
                            f.write(f"- {error}\n")
                        f.write("\n")

if __name__ == "__main__":
    print("Starting RSS feed health monitoring...")
    
    # Check RSS feed health
    status = check_rss_health()
    
    # Save status report
    save_status_report(status)
    
    # Print summary
    print_status_summary(status)
    
    # Create GitHub Action summary if running in CI
    create_github_action_summary(status)
    
    # Exit with appropriate code
    if status['overall_status'] == 'error':
        print("❌ Health check failed!")
        exit(1)
    elif status['overall_status'] == 'warning':
        print("⚠️  Health check completed with warnings")
        exit(0)
    else:
        print("✅ All RSS feeds healthy!")
        exit(0)
