from app import app, db
import re

with app.test_client() as c:
    with c.session_transaction() as sess:
        sess['user_id'] = 1
        sess['role'] = 'admin'
        sess['historical_mode_active'] = True
        sess['active_archive_id'] = 1
    
    response = c.get('/manage/faculty')
    html = response.get_data(as_text=True)
    
    if "No faculty" in html:
        print("Empty faculty message found.")
    
    print("Row count based on class='course-row faculty-row':", html.count("faculty-row"))
    
    # Save the output to a file for review
    with open('test_faculty.html', 'w', encoding='utf-8') as f:
        f.write(html)
    
    print("Saved test_faculty.html")
