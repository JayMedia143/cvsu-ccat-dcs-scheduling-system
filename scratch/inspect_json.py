import json
with open('live_conflicts.json') as f:
    data = json.load(f)
print("KEYS:", data.keys())
schedules = data.get('schedules', [])
print("COUNT:", len(schedules))
if schedules:
    print("SAMPLE RECORD:", schedules[0])
