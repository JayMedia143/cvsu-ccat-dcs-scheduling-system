import json

with open('live_conflicts.json') as f:
    data = json.load(f)

schedules = data.get('schedules', [])
pernala = [s for s in schedules if 'PERNALA' in str(s.get('faculty_name', '')).upper()]

print("SIR PERNALA'S SCHEDULE:")
for p in sorted(pernala, key=lambda x: (x.get('day', ''), x.get('start_time', ''))):
    print(f"{p.get('day')} | {p.get('start_time')}-{p.get('end_time')} | {p.get('course_code')} ({p.get('section_name')}) | {p.get('room_name')}")
