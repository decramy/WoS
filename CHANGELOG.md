# Changelog

All notable changes to WoS (WSJF on Steroids) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.4.0] - 2026-01-11

### Added
- **Dashboard Quick Create**: Add a story by title directly from the dashboard and jump straight to refinement.
- **Housekeeping Labels**: Housekeeping now surfaces all labels without stories (ordered by category/name) to clean up unused labels.

### Changed
- **License**: Project relicensed to GNU AGPL v3; README badge and license section updated accordingly.

### Fixed
- **Housekeeping Listing**: Unused labels are no longer truncated, ensuring visibility of every label needing attention.

## [2.3.0] - 2026-01-06

### Added
- **Hybrid Scoring Mode**: Each factor can now be set to "absolute" or "relative" scoring mode
  - `scoring_mode` field added to `ValueFactor` and `CostFactor` models
  - Absolute mode (default): uses answer score directly (1-5, etc.)
  - Relative mode: uses relative rankings (rank 1 = best)
  - Configure via Django Admin with inline editing
  - Migration 0020 adds the new field
  
- **Hybrid Report** (`/backlog/relative/report/`): Combines both scoring methods
  - Factors set to "absolute" contribute their answer score
  - Factors set to "relative" contribute normalized rankings
  - Same WSJF formula: Value ÷ Cost
  - Tooltips show which mode each factor uses
  
- **Normalized Relative Scoring**: Relative ranks are now scaled to match absolute scores
  - Uses each factor's answer options to determine score range (e.g., 1-5)
  - Rank 1 → max score, Rank N → min score (linear interpolation)
  - For value factors: rank 1 = highest score (best)
  - For cost factors: rank 1 = lowest score (best/cheapest)
  - Tooltips show: `#rank/total → normalized_score`
  
### Changed
- **Relative Ranking page** now only shows factors with `scoring_mode='relative'`
  - Displays message when no factors are set to relative mode
  - Link to Django Admin to configure factor scoring modes
  
- **Three-Zone Ranking System** for relative ranking:
  - **Ranked** (above first divider): Stories with assigned ranks (1, 2, 3...)
  - **Undefined** (between dividers): Stories not yet ranked - need attention
  - **No Score** (below second divider): Stories where the factor doesn't apply
  - Rank values: positive integer = ranked, `NULL` = undefined, `0` = no score
  - Visual distinction with color-coded borders and badges

### Fixed
- **Empty story list bug**: New relative factors now show all stories
  - Score records are auto-created for stories missing them
  - Previously, new factors showed no stories until absolute scores were set
  
- **Admin improvements**: 
  - `scoring_mode` column added to ValueFactor and CostFactor list views
  - Inline editing of scoring mode directly from list view
  - Filter by scoring mode

## [2.2.0] - 2026-01-05

### Added
- **Relative Ranking**: New page for ranking stories relative to each other
  - Access via 🔢 Rank button in navigation
  - Select Value or Cost factors to rank stories against
  - Drag-and-drop interface for intuitive ranking
  - Stories grouped by their absolute answer score
  - Ranked stories persist per factor via `relative_rank` field
  - Save rankings with visual feedback
  - Reset rankings to reload from database
  - Warning when leaving with unsaved changes
  
- **Relative Report**: New report page using relative rankings
  - Access via `/backlog/relative/report/` or from Relative Ranking page
  - Same WSJF formula: (sum of value section averages) ÷ (sum of cost section averages)
  - Value factor ranks are inverted (rank 1 → highest score)
  - Cost factor ranks used directly (rank 1 = lowest cost = best)
  - Tooltips showing factor breakdown per section
  - Row coloring based on result (green = best, red = worst)
  - Sortable columns, status and label filters
  
### Changed
- **New model fields**: Added `relative_rank` to both `StoryValueFactorScore` and `StoryCostFactorScore` models
  - Integer field to store relative position when ranking stories against each other
  - Migration 0019 adds the new fields

## [2.1.0] - 2026-01-04

### Added
- **Bulk Actions**: Perform actions on multiple stories at once
  - Select stories with checkboxes (individual or select all)
  - Bulk action bar appears when stories are selected
  - Supported actions:
    - 🏷️ Add Labels: Add labels to selected stories (modal with category grouping)
    - 🚩 Set Review: Flag selected stories for review
    - ✅ Clear Review: Remove review flag from selected stories
    - 🚫 Mark Blocked: Set blocked reason on selected stories (with input modal)
    - 📦 Archive / 📤 Unarchive: Archive or unarchive selected stories
    - 🗑️ Delete: Delete selected stories (with confirmation)
  - History tracking for bulk blocked and label changes
  - 8 new tests for bulk actions (116 total tests)

### Changed
- **Story list UI improvements**:
  - Labels now shown on second line below story title
  - Review required flag (🚩) shown before story title instead of separate column
  - Reduced table columns for cleaner layout
  
- **Report page UI improvements**:
  - Labels now shown on second line below story title
  - Review required flag (🚩) shown before story title

## [2.0.0] - 2026-01-04

### Breaking Changes
- **Epic model removed**: The Epic container model has been removed from the system
  - Stories are now standalone entities and don't require an epic
  - Migration 0017 automatically converts epic names to labels
  - All existing epics are migrated to a "Former Epics" label category

### Added
- **Label system**: New flexible categorization replacing epics
  - `LabelCategory` model: Categories with color and icon (e.g., Epic, Team, Priority)
  - `Label` model: Individual labels within categories
  - Many-to-many relationship: Stories can have multiple labels
  - Auto-migration: All former epics converted to labels in "Former Epics" category
  
- **Label filtering**: Intuitive multi-select filter across all list views
  - Dropdown per label category for organized selection
  - AND logic: Filter to stories with ALL selected labels
  - Applied labels shown with × remove button
  - Consistent filter on Stories, Report, Kanban, and WBS pages
  - Preserves other URL parameters (sort, status, etc.)
  - 10 new tests for label filtering functionality

### Changed
- **Performance optimizations**: Significant query efficiency improvements
  - `computed_status` property now uses prefetched data (avoids N+1 queries)
  - `_calculate_story_score` accepts pre-loaded sections to avoid repeated queries
  - Dashboard housekeeping reuses already-loaded factor IDs
  - Story signal uses `bulk_create` with `ignore_conflicts` instead of loop
  - Added database indexes on frequently queried fields:
    - Single-field: `archived`, `status`, `review_required`, `planned`, `started`, `finished`
    - Composite: `(archived, status)`, `(archived, created_at)`

- **Correct undefined score handling**: `computed_status` now properly distinguishes between:
  - Undefined scores (answer=None) → story is 'idea'
  - Actual scores (even score=0) → counted as scored
  
### Removed
- `Epic` model and all related views (epic_list, epic_detail, epic_create, epic_update)
- `epic` ForeignKey on Story model
- `/backlog/epics/` and `/backlog/epic/<id>/` URL patterns
- Epic-related tests (91 → 108 tests after refactoring)

## [1.2.0] - 2026-01-01

### Added
- **Statistics Dashboard Section**: New informational metrics about backlog health
  - Backlog Overview: Total/active/archived stories and epics counts
  - Status Distribution: Breakdown of stories by status
  - Biggest Epics: Top 5 epics by active story count
  - Recently Completed: Stories completed in the last 30 days
  - Oldest Open Stories: Oldest open items in the backlog
  - Blocking Stories: Stories that block other work (most dependents)
- Added 4 new tests for statistics functionality (120 total tests)

### Changed
- **Review Required moved to first position**: Now the first dashboard section for priority visibility
- Reordered dashboard summary cards to put Review first

## [1.1.0] - 2026-01-01

### Added
- **Housekeeping Dashboard Section**: New data integrity monitoring and cleanup tools
  - Orphaned Stories: Stories whose epic has been deleted
  - Orphaned Value/Cost Scores: Scores for deleted stories (with auto-cleanup)
  - Orphaned Dependencies: Dependencies referencing deleted stories (with auto-cleanup)
  - Orphaned History: History entries for deleted stories (with auto-cleanup)
  - Stale Value/Cost Scores: Scores for deleted factors (with auto-cleanup)
  - Empty Epics: Epics without any stories (informational)
  - Duplicate Dependencies: Same dependency recorded multiple times
  - Summary count in dashboard header
  - One-click cleanup buttons for fixable issues
- Added 7 new tests for housekeeping functionality (116 total tests)

## [1.0.0] - 2026-01-01

### Added
- **Views modularization**: Split monolithic `views.py` (1535 lines) into focused modules:
  - `views/helpers.py` - Shared utility functions
  - `views/dashboard.py` - Dashboard view
  - `views/epics.py` - Epic CRUD operations
  - `views/stories.py` - Story management
  - `views/report.py` - WSJF scoring report
  - `views/kanban.py` - Kanban board
  - `views/wbs.py` - Work Breakdown Structure
  - `views/health.py` - Health check endpoint

### Changed
- Improved code organization for better maintainability

## [0.9.0] - 2026-01-01

### Fixed
- **Undefined vs Zero Score distinction**: Scores now properly distinguish between "undefined" (not yet scored) and an explicit score of 0
  - Made `answer` field nullable in `StoryValueFactorScore` and `StoryCostFactorScore`
  - `answer=None` means undefined/not scored
  - `answer` with `score=0` is a valid explicit score
  - Dashboard correctly detects stories needing scoring
  - Updated signal to create scores with `answer=None` for new stories

## [0.8.0] - 2026-01-01

### Added
- **Dashboard feature**: New dashboard showing stories that need attention
  - Needs Scoring: Stories with missing or undefined factor scores
  - Needs Refinement: Stories in 'idea' status (missing goal/workitems)
  - Rotting Stories: Stories stuck in started/planned/blocked for too long
  - Review Required: Stories flagged for review
  - Summary counts and health metrics
  - Configurable rotting thresholds (14 days started, 30 days planned, 7 days blocked)
- Added 15 new tests for dashboard functionality

## [0.7.0] - 2026-01-01

### Changed
- **URL restructuring**: Consistent RESTful URL patterns
  - `/backlog/` → redirects to dashboard
  - `/backlog/dashboard/` → Dashboard
  - `/backlog/epics/` → Epic list
  - `/backlog/epic/<id>/` → Epic detail
  - `/backlog/stories/` → Story list  
  - `/backlog/story/<id>/` → Story detail
  - `/backlog/report/` → WSJF report
  - `/backlog/kanban/` → Kanban board
  - `/backlog/wbs/` → Work Breakdown Structure
  - `/backlog/health/` → Health check

## [0.6.0] - 2025-12-31

### Added
- **Code documentation**: Comprehensive docstrings and comments throughout codebase
- **README improvements**: Updated with project overview, features, installation, and usage
- Prepared codebase for open-source publication

## [0.5.0] - 2025-12-31

### Added
- **Detailed tooltips**: Hover tooltips on report scores showing factor breakdown
  - Each section score shows individual factor scores with descriptions
  - Total value/cost shows section breakdown
  - Result shows calculation formula

## [0.4.0] - 2025-12-31

### Changed
- **Score calculation update**: Changed from sum of all scores to sum of section averages
  - Value = sum of (average score per value section)
  - Cost = sum of (average score per cost section)
  - Result = Value / Cost
  - This gives equal weight to each section regardless of factor count

## [0.3.0] - 2025-12-31

### Added
- **Tweak mode**: Temporary score adjustments in the report view
  - Allows "what-if" analysis without persisting changes
  - Reset button to restore original scores
  - Visual indication when tweaks are active

## [0.2.0] - 2025-12-30

### Added
- **Comprehensive test suite**: 94 regression tests covering:
  - Model creation and relationships
  - `computed_status` property logic
  - Epic and Story CRUD operations
  - Archiving functionality with cascade
  - History tracking
  - Kanban board moves
  - Report calculations
  - WBS dependencies
  - Story refinement

## [0.1.0] - 2025-12-22

### Added
- Initial release of WoS (WSJF on Steroids)
- **Epic management**: Create, edit, archive epics
- **Story management**: Full story lifecycle with refinement
- **WSJF scoring**: Value and Cost factors with configurable sections
- **Kanban board**: Visual workflow with drag-and-drop
- **Report view**: Priority scoring with filtering
- **WBS view**: Work Breakdown Structure with dependencies
- **Story dependencies**: Link stories with depends-on relationships
- **Story history**: Track all changes to stories
- **Archive/unarchive**: Soft delete for epics and stories
- **Review flag**: Mark stories requiring review
- **Health endpoint**: Container orchestration health check
- **Dark/light themes**: CSS theme support
- **Docker support**: Dockerfile and docker-compose configuration
