import os
import re
import csv

template_dir = r'c:\WFH\jeremy\48. CvSU_Scheduling_System-Version-2.61_send\CvSU_Scheduling_System-Version-2 - antigravity_2_claude - Copy\templates'
results = []

def scan_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Improved regex: find ID and then find the NEXT <div class="modal-dialog ...">
    # We look for <div id="...Modal" and then the first <div class="modal-dialog" that follows.
    modal_blocks = re.findall(r'<div\s+[^>]*id=["\']([^"\']+)["\'][^>]*class=["\']modal fade["\'].*?<div\s+[^>]*class=["\'](modal-dialog[^"\']+)["\']', content, re.DOTALL)
    
    rel_path = os.path.relpath(filepath, template_dir)
    
    for mid, classes in modal_blocks:
        has_centered = 'modal-dialog-centered' in classes
        has_below = 'modal-dialog-below-nav' in classes
        results.append({
            'file': rel_path,
            'id': mid,
            'centered': has_centered,
            'below': has_below,
            'classes': classes
        })

for root, dirs, files in os.walk(template_dir):
    for file in files:
        if file.endswith('.html'):
            scan_file(os.path.join(root, file))

with open('modal_audit.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=['file', 'id', 'centered', 'below', 'classes'])
    writer.writeheader()
    writer.writerows(results)
