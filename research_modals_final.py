import os
import re
import sys

# Set IO to utf-8 for emojis
sys.stdout.reconfigure(encoding='utf-8')

template_dir = r'c:\WFH\jeremy\48. CvSU_Scheduling_System-Version-2.61_send\CvSU_Scheduling_System-Version-2 - antigravity_2_claude - Copy\templates'
results = []

# Improved strategy: 
# 1. Split content by '<div' to handle each element or start of elements
# 2. Or better yet, find all blocks starting with '<div class="modal fade"' up to standard closing </div> blocks
# Actually, the most reliable way in non-standard HTML is to find the ID and search the next few lines for 'modal-dialog'

def scan_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find all modal ID declarations
    # id="somethingModal"
    id_matches = re.finditer(r'id=["\']([^"\']*Modal[^"\']*)["\']', content)
    
    for match in id_matches:
        mid = match.group(1)
        # Look at the next 500 characters after the ID
        start_pos = match.end()
        snippet = content[start_pos:start_pos + 500]
        
        # Find the first modal-dialog class in this snippet
        dialog_match = re.search(r'class=["\'](modal-dialog[^"\']*)["\']', snippet)
        
        if dialog_match:
            classes = dialog_match.group(1)
            has_centered = 'modal-dialog-centered' in classes
            has_below = 'modal-dialog-below-nav' in classes
            results.append({
                'file': os.path.basename(filepath),
                'id': mid,
                'centered': has_centered,
                'below': has_below,
                'classes': classes
            })

for root, dirs, files in os.walk(template_dir):
    for file in files:
        if file.endswith('.html'):
            scan_file(os.path.join(root, file))

print("| File | Modal ID | Centered | Below Nav | Action |")
print("| :--- | :--- | :---: | :---: | :--- |")
for r in results:
    c = "✅" if r['centered'] else "❌"
    b = "✅" if r['below'] else "❌"
    action = "None"
    if not r['centered'] and not r['below']:
        action = "Add both"
    elif not r['centered']:
        action = "Add centered"
    elif not r['below']:
        action = "Add below-nav"
    print(f"| {r['file']} | `{r['id']}` | {c} | {b} | {action} |")
