import os
import re

def count_actual_features():
    total_functions = 0
    base_path = "."
    
    html_count = 0
    for root, dirs, files in os.walk(os.path.join(base_path, 'templates')):
        for file in files:
            if file.endswith('.html'):
                with open(os.path.join(root, file), 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    html_count += len(re.findall(r'<button', content))
                    html_count += len(re.findall(r'<input', content))
                    html_count += len(re.findall(r'<select', content))
                    html_count += len(re.findall(r'<textarea', content))
                    html_count += len(re.findall(r'class="modal', content))
                    html_count += len(re.findall(r'<form', content))
                    html_count += len(re.findall(r'class="badge', content))
                    html_count += len(re.findall(r'data-bs-toggle="tooltip"', content))

    logic_count = 0
    route_count = 0
    app_path = os.path.join(base_path, 'app.py')
    if os.path.exists(app_path):
        with open(app_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            route_count = len(re.findall(r'@app\.route', content))
            logic_count += route_count
            logic_count += len(re.findall(r'flash\(', content))
            logic_count += len(re.findall(r'jsonify\(', content))
            logic_count += len(re.findall(r'redirect\(', content))
            logic_count += len(re.findall(r'if not', content))
            logic_count += len(re.findall(r'request\.form', content))

    ga_path = os.path.join(base_path, 'genetic_algorithm.py')
    ga_count = 0
    if os.path.exists(ga_path):
        with open(ga_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            ga_count += len(re.findall(r'def ', content))
            ga_count += len(re.findall(r'if ', content))
    
    total = html_count + logic_count + ga_count
    print(f"Routes: {route_count}")
    print(f"HTML Count: {html_count}")
    print(f"Logic Count: {logic_count}")
    print(f"GA Count: {ga_count}")
    print(f"Total: {total}")

if __name__ == "__main__":
    count_actual_features()

