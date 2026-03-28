---
name: Seeder Updates — 2026-03-22 Session B
description: seeder1–9 updated with sex/academic_rank/highest_educational_attainment/available_days for all faculty, HC-27/28/29 constraints added, room_departments added to B-series rooms
type: project
---

## Session Summary — 2026-03-22 (Session B)

### Seeders Updated: seeder1.py through seeder9.py
**seed_db.py NOT touched** — only seeder1–9 were modified.

### Change A+B — Faculty: 4 new fields added

All 9 seeders now populate:
- `sex` — 'M' or 'F' for real faculty; `None` for TBA
- `academic_rank` — e.g., 'Assistant Professor I', 'Instructor II', etc.
- `highest_educational_attainment` — e.g., 'Master of Arts in Teaching'
- `available_days` — Mon–Fri for Full-time faculty; Mon–Sat for Part-time; Mon–Sat for TBA

Faculty() constructor updated to pass all 4 via `f.get()`:
```python
Faculty(..., sex=f.get('sex'), academic_rank=f.get('rank', ''),
        highest_educational_attainment=f.get('attainment', ''),
        available_days=f.get('days', 'Monday,Tuesday,Wednesday,Thursday,Friday,Saturday'))
```

### Standard Faculty Values (consistent across all seeders)

| eid | sex | rank | attainment | days |
|-----|-----|------|------------|------|
| DAS-001 Gabriela Silang | F | Assistant Professor II | Master of Arts in Education | Mon–Fri |
| DAS-002 Emilio Aguinaldo | M | Associate Professor I | Doctor of Philosophy | Mon–Fri |
| DAS-003 Andres Bonifacio | M | Instructor I | Bachelor of Science | Mon–Sat |
| DAS-004 Melchora Aquino | F | Instructor II | Master of Arts | Mon–Sat |
| DAS-005 Jose Rizal | M | Associate Professor III | Doctor of Philosophy | Mon–Fri |
| DAS-006 Marcelo Del Pilar | M | Instructor III | Master of Arts | Mon–Sat |
| DAS-007 Pilar Hidalgo Lim | F | Assistant Professor I | Master of Education | Mon–Fri |
| DAS-008 Trinidad Tecson | F | Instructor I | Bachelor of Arts | Mon–Sat |
| DAS-009 Josephine Bracken | F | Instructor II | Master of Arts | Mon–Fri |
| DAS-010 Gregoria de Jesus | F | Instructor III | Master of Education | Mon–Sat |
| DAS-011 Gat Andres Luna | M | Associate Professor I | Doctor of Philosophy | Mon–Fri |
| DAS-012 Claro Recto | M | Associate Professor II | Doctor of Laws | Mon–Fri |
| DTE-001 Apolinario Mabini | M | Assistant Professor I | Master of Arts in Teaching | Mon–Fri |
| DTE-002 Leonor Briones | F | Instructor III | Master of Education | Mon–Sat |
| DTE-003 Sara Duterte | F | Associate Professor II | Doctor of Education | Mon–Fri |
| DTE-004 Armin Luistro | M | Instructor II | Master of Arts in Education | Mon–Sat |
| DTE-005 Benigno Aquino Jr | M | Associate Professor I | Doctor of Philosophy | Mon–Fri |
| DTE-006 Jose Abad Santos | M | Instructor I | Master of Science in Education | Mon–Sat |
| DTE-007 Celso Manguerra | M | Assistant Professor II | Master of Education | Mon–Fri |
| DTE-008 Felicidad Montejo | F | Instructor I | Bachelor of Science in Education | Mon–Sat |
| CEN-001 Lapu-Lapu | M | Assistant Professor III | Master of Engineering | Mon–Fri |
| CEN-002 Antonio Luna | M | Instructor I | Bachelor of Science in Engineering | Mon–Sat |
| CEN-003 Teodora Alonso | F | Assistant Professor I | Master of Science | Mon–Fri |
| CEN-004 Baldomero Aguinaldo | M | Instructor II | Master of Engineering | Mon–Sat |
| CEN-005 Francisco Baltazar | M | Associate Professor I | Doctor of Engineering | Mon–Fri |
| CEN-006 Emilio Jacinto | M | Instructor III | Bachelor of Science in Engineering | Mon–Sat |
| DCS-001 Juan Luna | M | Assistant Professor II | Master of Science in Computer Science | Mon–Fri |
| DCS-002 Nicolas Zafra | M | Instructor II | Bachelor of Science in Information Technology | Mon–Sat |
| DCS-003 Graciano Lopez Jaena | M | Associate Professor I | Doctor of Information Technology | Mon–Fri |
| DCS-004 Pedro Paterno | M | Instructor III | Master of Science | Mon–Sat |
| DCS-005 Paciano Rizal | M | Instructor I | Bachelor of Science in Computer Science | Mon–Fri |
| DCS-006 Tomas Pinpin | M | Instructor II | Master of Science in Information Technology | Mon–Sat |

### Change C — Constraints: HC-27, HC-28, HC-29 added to all 9 seeders

All 9 seeders now have 29 hard constraints (was 26). Added after HC-26:
- `EARLY_START` → (HC-27) Early Start Enforcement
- `DIV4_SLOT_ALIGNMENT` → (HC-28) Divisible-4 Slot Alignment
- `FACULTY_DAY_SPLIT` → (HC-29) Faculty Day Split

### Change D+E — Rooms: room_departments on B-series rooms

B1–B6 (and any B-series) now have `room_departments='Department of Computer Studies'`.
Room() constructor updated: `room_departments=r.get('room_depts', '')`.
A-series, University Field, T.B.A., C-series, MediaLab → `room_departments=''` (no restriction).
