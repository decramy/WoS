# WoS - WSJF on Steroids

## Overview
WoS is a web application designed to help teams manage their backlog of work items using WSJF (Weighted Shortest Job First) prioritization. The application provides a user-friendly interface to create, view, and manage epics and stories with value/cost factor scoring, kanban boards, and comprehensive reporting.

## Features
- **Epic & Story Management**: Create and manage epics and stories with rich metadata
- **WSJF Scoring**: Configure value factors and cost factors with customizable scoring sections
- **Computed Status**: Automatic status tracking (new → todo → planned → started → done/blocked)
- **Kanban Board**: Drag-and-drop interface to move stories through workflow stages
- **Reporting**: Per-section averages, value/cost ratios with filtering
- **Dark/Light Theme**: Toggle between themes with OS preference detection
- **Health Check**: `/backlog/health/` endpoint for container orchestration

## Quick Start

### Option 1: Docker (Recommended)
```bash
docker compose up --build
```
Access at `http://localhost:8000/`

### Option 2: Local Development
```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Start development server
python manage.py runserver
```
Access at `http://127.0.0.1:8000/`

## Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_SECRET_KEY` | `your-secret-key` | Secret key for production |
| `DJANGO_DEBUG` | `False` | Enable debug mode |
| `DJANGO_ALLOWED_HOSTS` | `*` | Comma-separated allowed hosts |

## URL Structure
- `/` - Redirects to `/backlog/`
- `/backlog/` - Epics overview (main dashboard)
- `/backlog/stories/` - Stories list with filters
- `/backlog/kanban/` - Kanban board
- `/backlog/report/` - WSJF report with scoring
- `/backlog/health/` - Health check endpoint
- `/admin/` - Django admin interface

## Contributing
Contributions are welcome! Please open an issue or submit a pull request.

## License
This project is licensed under the MIT License. See the LICENSE file for details.