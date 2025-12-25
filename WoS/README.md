# WoS - WSJF on Steroids

A Django web application for managing product backlogs using **WSJF (Weighted Shortest Job First)** prioritization with customizable value and cost factors.

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Django](https://img.shields.io/badge/Django-5.x-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## Overview

WoS helps teams prioritize their backlog by calculating a WSJF score for each story based on configurable value and cost dimensions. Unlike traditional WSJF implementations, WoS allows you to:

- Define multiple **value factor sections** (e.g., Business Value, User Experience, Strategic Alignment)
- Define multiple **cost factor sections** (e.g., Development Effort, Technical Risk, Dependencies)
- Score each factor with customizable answer options
- View prioritized reports with detailed breakdowns
- Manage workflow using a Kanban board

## Features

### Backlog Management
- **Epics**: Group related stories into epics
- **Stories**: Create stories with goals, workitems, and detailed descriptions
- **Dependencies**: Define relationships between stories
- **History Tracking**: Automatic audit trail for all story changes

### WSJF Scoring
- **Customizable Factors**: Define your own value and cost dimensions via Django Admin
- **Section Averages**: Each section's score is the average of its factors
- **WSJF Score**: `Result = Σ(value section averages) / Σ(cost section averages)`
- **Detailed Tooltips**: Hover over scores to see the calculation breakdown

### Workflow
- **Computed Status**: Automatic status based on dates and data completeness
  - `idea` → `ready` → `planned` → `started` → `done`/`blocked`
- **Kanban Board**: Drag-and-drop interface to move stories through workflow stages
- **Archive Support**: Archive completed or obsolete epics/stories

### Reporting
- **Priority Report**: Stories ranked by WSJF score with filtering
- **Tweak Mode**: Temporarily adjust scores to explore "what-if" scenarios
- **WBS View**: Work Breakdown Structure showing dependencies

### User Experience
- **Dark/Light Theme**: Toggle between themes or use OS preference
- **Responsive Design**: Works on desktop and tablet
- **Search & Filter**: Find stories by text, epic, status, or review flag

## Quick Start

### Option 1: Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/decramy/WoS.git
cd WoS/WoS

# Start with Docker Compose
docker compose up --build
```

Access at `http://localhost:8000/`

### Option 2: Local Development

```bash
# Clone the repository
git clone https://github.com/decramy/WoS.git
cd WoS/WoS

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Create superuser for admin access
python manage.py createsuperuser

# Start development server
python manage.py runserver
```

Access at `http://127.0.0.1:8000/`

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_SECRET_KEY` | (generated) | Secret key for production |
| `DJANGO_DEBUG` | `False` | Enable debug mode |
| `DJANGO_ALLOWED_HOSTS` | `*` | Comma-separated allowed hosts |

### Setting Up Factors

1. Access Django Admin at `/admin/`
2. Create **Value Factor Sections** (e.g., "Business Value", "User Experience")
3. Add **Value Factors** to each section (e.g., "Revenue Impact", "Customer Satisfaction")
4. Create **Value Factor Answers** for each factor (e.g., "High (5)", "Medium (3)", "Low (1)")
5. Repeat for **Cost Factor Sections/Factors/Answers**

## URL Structure

| URL | Description |
|-----|-------------|
| `/` | Redirects to `/backlog/` |
| `/backlog/` | Epics overview (main dashboard) |
| `/backlog/stories/` | Stories list with filters |
| `/backlog/story/new/` | Create new story |
| `/backlog/story/<id>/refine/` | Edit/refine a story |
| `/backlog/kanban/` | Kanban board |
| `/backlog/report/` | WSJF priority report |
| `/backlog/wbs/` | Work Breakdown Structure |
| `/backlog/health/` | Health check endpoint |
| `/admin/` | Django admin interface |

## Project Structure

```
WoS/
├── backlog/                 # Main Django app
│   ├── models.py           # Data models (Epic, Story, Factors, etc.)
│   ├── views.py            # View functions
│   ├── urls.py             # URL routing
│   ├── admin.py            # Admin configuration
│   ├── tests.py            # Test suite (94 tests)
│   ├── templates/          # HTML templates
│   └── migrations/         # Database migrations
├── static/                  # Static files (CSS, JS)
│   ├── css/
│   │   ├── base.css        # Main styles
│   │   ├── dark.css        # Dark theme
│   │   └── light.css       # Light theme
│   └── js/
│       └── app.js          # Client-side JavaScript
├── templates/               # Base templates
├── wos/                     # Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── manage.py
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## Testing

Run the test suite:

```bash
python manage.py test backlog.tests
```

The test suite includes 94 tests covering:
- Model validation and computed properties
- CRUD operations for epics and stories
- Kanban board movements
- Report calculations
- Archiving/unarchiving functionality
- History tracking

## Score Calculation

The WSJF score is calculated as follows:

1. **Per-Section Average**: For each value/cost section, calculate the average of its factor scores
2. **Total Value**: Sum all value section averages
3. **Total Cost**: Sum all cost section averages
4. **Result**: `Total Value / Total Cost`

Example:
```
Value Sections:
  - Business Value: avg(5, 3) = 4.0
  - User Experience: avg(4, 4, 2) = 3.3
  Total Value = 4.0 + 3.3 = 7.3

Cost Sections:
  - Development Effort: avg(3, 2) = 2.5
  - Risk: avg(1) = 1.0
  Total Cost = 2.5 + 1.0 = 3.5

Result = 7.3 / 3.5 = 2.09
```

Higher scores indicate better value-to-cost ratio and should be prioritized.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License. See the [LICENSE](../LICENSE) file for details.

## Acknowledgments

- Built with [Django](https://www.djangoproject.com/)
- Inspired by SAFe WSJF methodology