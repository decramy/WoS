"""
Changelog view for WoS backlog application.

Displays the project changelog in the web application.
"""
import os

from django.conf import settings
from django.shortcuts import render


def changelog(request):
    """Display the project changelog.
    
    Reads CHANGELOG.md and renders it in the web application.
    """
    changelog_path = os.path.join(settings.BASE_DIR, 'CHANGELOG.md')
    
    changelog_content = ""
    if os.path.exists(changelog_path):
        with open(changelog_path, 'r', encoding='utf-8') as f:
            changelog_content = f.read()
    
    # Parse markdown into structured data for template
    versions = []
    current_version = None
    current_section = None
    
    for line in changelog_content.split('\n'):
        line = line.rstrip()
        
        # Version header: ## [1.0.0] - 2026-01-01
        if line.startswith('## ['):
            if current_version:
                versions.append(current_version)
            
            # Parse version and date
            parts = line[4:].split('] - ')
            version_num = parts[0] if parts else ''
            version_date = parts[1] if len(parts) > 1 else ''
            
            current_version = {
                'version': version_num,
                'date': version_date,
                'sections': []
            }
            current_section = None
            
        # Section header: ### Added, ### Changed, ### Fixed
        elif line.startswith('### ') and current_version:
            section_name = line[4:]
            current_section = {
                'name': section_name,
                'items': []
            }
            current_version['sections'].append(current_section)
            
        # List item: - **Feature**: Description
        elif line.startswith('- ') and current_section:
            item = line[2:]
            # Parse bold title if present
            if item.startswith('**') and '**:' in item:
                title_end = item.index('**:', 2)
                title = item[2:title_end]
                description = item[title_end + 3:].strip()
                current_section['items'].append({
                    'title': title,
                    'description': description,
                    'subitems': []
                })
            else:
                current_section['items'].append({
                    'title': None,
                    'description': item,
                    'subitems': []
                })
                
        # Sub-item:   - Sub description
        elif line.startswith('  - ') and current_section and current_section['items']:
            subitem = line[4:]
            current_section['items'][-1]['subitems'].append(subitem)
    
    # Don't forget the last version
    if current_version:
        versions.append(current_version)
    
    context = {
        'versions': versions,
        'raw_changelog': changelog_content,
    }
    return render(request, 'backlog/changelog.html', context)
