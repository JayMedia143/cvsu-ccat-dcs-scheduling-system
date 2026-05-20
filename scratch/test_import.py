print("Starting import test...")
from app import app
print("Imported app successfully")
with app.app_context():
    print("In app context")
