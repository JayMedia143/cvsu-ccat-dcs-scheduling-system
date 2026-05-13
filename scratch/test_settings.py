import sys
import os

# Add parent directory to path
sys.path.append(os.path.abspath('.'))

from app import app, db, SystemSettings, User

def run_test():
    # Disable CSRF for testing
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['TESTING'] = True
    
    with app.test_request_context():
        # Let's check the current settings first
        settings = SystemSettings.query.first()
        print("Initial evening_start_hour:", settings.evening_start_hour)
        
        # Let's simulate saving settings
        with app.test_client() as client:
            admin = User.query.filter_by(username='admin1').first()
            if not admin:
                print("admin1 not found!")
                return
            
            with client.session_transaction() as sess:
                sess['user_id'] = admin.id
                sess['username'] = admin.username
                sess['role'] = admin.role
                sess['dept'] = admin.department
            
            payload = {
                'start_hour': '7',
                'end_hour': '20',
                'evening_start_hour': '18', # 6:00 PM
                'days': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'],
                'blocked_slots_json': '[]'
            }
            
            response = client.post('/settings', data=payload, headers={'Referer': 'http://localhost/dashboard'}, follow_redirects=True)
            print("Response code:", response.status_code)
            
            # Check database settings now
            db.session.expire_all()
            settings = SystemSettings.query.first()
            print("Updated evening_start_hour in DB:", settings.evening_start_hour)
            assert settings.evening_start_hour == 18, "Failed to update evening_start_hour!"
            print("SUCCESS: evening_start_hour updated to 18 correctly!")

if __name__ == '__main__':
    run_test()
