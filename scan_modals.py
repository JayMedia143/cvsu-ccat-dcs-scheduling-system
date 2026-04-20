import os
import re

template_dir = r'c:\WFH\jeremy\48. CvSU_Scheduling_System-Version-2.61_send\CvSU_Scheduling_System-Version-2 - antigravity_2_claude - Copy\templates'
results = []

def scan_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find all modal declarations
    # Look for id="..." and followed by class="modal-dialog ..."
    modals = re.findall(r'id=["\']([^"\']+)Modal[^"\']*["\'].*?class=["\']modal-dialog\s+([^"\']+)["\']', content, re.DOTALL)
    
    # Also find those that just have modal-dialog class without extra classes yet
    modals_basic = re.findall(r'id=["\']([^"\']+)Modal[^"\']*["\'].*?class=["\']modal-dialog["\']', content, re.DOTALL)
    
    rel_path = os.path.relpath(filepath, template_dir)
    
    for mid, classes in modals:
        has_centered = 'modal-dialog-centered' in classes
        has_below = 'modal-dialog-below-nav' in classes
        results.append({
            'file': rel_path,
            'id': mid + 'Modal',
            'centered': has_centered,
            'below': has_below,
            'classes': f'modal-dialog {classes}'
        })
        
    for mid in modals_basic:
        results.append({
            'file': rel_path,
            'id': mid + 'Modal',
            'centered': False,
            'below': False,
            'classes': 'modal-dialog'
        })

for root, dirs, files in os.walk(template_dir):
    for file in files:
        if file.endswith('.html'):
            scan_file(os.path.join(root, file))

print(f"{'File':<40} | {'Modal ID':<30} | {'Centered':<10} | {'Below Nav':<10}")
print("-" * 100)
for r in results:
    c = "YES" if r['centered'] else "NO"
    b = "YES" if r['below'] else "NO"
    print(f"{r['file']:<40} | {r['id']:<30} | {c:<10} | {b:<10}")
