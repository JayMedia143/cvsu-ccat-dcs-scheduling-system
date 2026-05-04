"""export_schedule.py — outputs SEED_SCHEDULES as Python code for injection into seeder11.py"""
import sys, io, importlib.util

old = sys.stdout; sys.stdout = io.StringIO()
spec = importlib.util.spec_from_file_location("sched", "generate_seed_schedule.py")
mod  = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
sys.stdout = old

schedule = mod.schedule

print("SEED_SCHEDULES = [")
for s in sorted(schedule, key=lambda x:(x['section'], x['course'], x['day'], x['start'])):
    fac = s['faculty'] if s['faculty'] else None
    print(f"    {{'section': {repr(s['section'])}, 'course': {repr(s['course'])}, "
          f"'faculty': {repr(fac)}, 'room': {repr(s['room'])}, "
          f"'day': {repr(s['day'])}, 'start': {s['start']}, 'end': {s['end']}, "
          f"'type': {repr(s['type'])}}},")
print("]")
print(f"# Total: {len(schedule)} sessions")
