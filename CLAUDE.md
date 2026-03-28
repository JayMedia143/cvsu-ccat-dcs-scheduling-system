# CvSU Scheduling System v2 — Claude Context

## Project Overview
Automated class scheduling system for Cavite State University (CvSU).
Uses a **Genetic Algorithm** to generate conflict-free class schedules based on constraints.

## Tech Stack
- **Backend**: Python / Flask 3.1.1
- **Database**: SQLite (`site.db`) via Flask-SQLAlchemy
- **Frontend**: Jinja2 templates + Vanilla JS + custom CSS
- **Algorithm**: Custom Genetic Algorithm (`genetic_algorithm.py`)
- **Exports**: PDF (WeasyPrint), Excel (openpyxl), CSV (pandas)
- **Virtual env**: `venv/`

## Key Files
| File | Purpose |
|------|---------|
| `app.py` | Main Flask app — all routes, DB models, auth |
| `genetic_algorithm.py` | Core scheduling engine |
| `seed_db.py` | Database seed/init script |
| `site.db` | SQLite database |
| `static/css/style.css` | Main stylesheet |
| `static/js/main.js` | Frontend JS |
| `templates/` | 31 Jinja2 HTML templates |

## Project Structure
```
app.py                  # Flask app entry point
genetic_algorithm.py    # Genetic algorithm for scheduling
seed_db.py              # DB initialization
site.db                 # SQLite database
requirements.txt        # Python dependencies
static/
  css/style.css
  js/main.js
  assets/
  profile_pics/
templates/              # All HTML templates (31 files)
  base.html
  login.html
  dashboard.html
  manage_courses.html
  manage_faculty.html
  generate_schedule.html
  manage_constraints.html
  ...
venv/                   # Python virtual environment
```

## Key Features
- Role-based auth (admin / regular user)
- Course, faculty, room, section management
- Schedule generation with hard & soft constraints
- Conflict detection and constraint validation
- Import/export (PDF, Excel, CSV)
- Archive functionality for historical schedules
- Real-time progress tracking during generation

## Running the App
```bash
# Activate virtual environment
source venv/Scripts/activate   # Windows bash

# Run Flask
python app.py
```

## Notes
- Database is SQLite — file is `site.db` in project root
- Main logic is in `app.py` (large file ~227KB) and `genetic_algorithm.py` (~97KB)
- Always activate `venv` before running or installing packages
