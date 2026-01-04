"""
Views package for WoS backlog application.

This package splits view functions into logical modules for maintainability:
- dashboard: Dashboard showing stories needing attention
- stories: Story refinement and list views
- report: WSJF scoring report
- kanban: Kanban board with drag-and-drop
- wbs: Work Breakdown Structure with dependencies
- health: Health check endpoint
- helpers: Shared helper functions

All view functions are re-exported here for backwards compatibility with urls.py.
"""

# Re-export all views for backwards compatibility
from .dashboard import dashboard
from .health import health
from .kanban import kanban_move, kanban_view
from .report import _calculate_story_score, report_view
from .stories import bulk_action, create_label, create_story_refine, refine_story, story_list
from .wbs import wbs_add_dependency, wbs_remove_dependency, wbs_view
from .changelog import changelog

__all__ = [
    # Dashboard
    'dashboard',
    # Stories
    'refine_story',
    'create_story_refine',
    'story_list',
    'bulk_action',
    'create_label',
    # Report
    'report_view',
    '_calculate_story_score',
    # Kanban
    'kanban_view',
    'kanban_move',
    # WBS
    'wbs_view',
    'wbs_add_dependency',
    'wbs_remove_dependency',
    # Health
    'health',
    # Changelog
    'changelog',
]
