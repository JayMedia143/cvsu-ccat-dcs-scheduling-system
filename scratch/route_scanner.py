import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

import app

def scan():
    url_map = app.app.url_map
    view_functions = app.app.view_functions
    
    routes_info = []
    
    for rule in url_map.iter_rules():
        endpoint = rule.endpoint
        if endpoint == 'static':
            continue
            
        func = view_functions.get(endpoint)
        doc = func.__doc__ if func else ""
        if doc:
            doc = doc.strip().split('\n')[0]
        else:
            doc = "No description available"
            
        # Inspect source code to see if role_required is used
        roles = []
        if func:
            try:
                import inspect
                source = inspect.getsource(func)
                # find @role_required(...)
                import re
                match = re.search(r'@role_required\((.*?)\)', source)
                if match:
                    roles = [r.strip().replace("'", "").replace('"', '') for r in match.group(1).split(',')]
                elif '@login_required' in source:
                    roles = ['login_required']
                else:
                    roles = ['public']
            except Exception as e:
                roles = ['unknown']
                
        routes_info.append({
            'endpoint': endpoint,
            'rule': str(rule),
            'methods': list(rule.methods - {'OPTIONS', 'HEAD'}),
            'doc': doc,
            'roles': roles,
            'function_name': func.__name__ if func else endpoint
        })
        
    routes_info.sort(key=lambda x: x['rule'])
    
    # Save as Markdown
    with open('scratch/detected_routes.md', 'w', encoding='utf-8') as f:
        f.write("# Detected Routes and Features\n\n")
        f.write("| URL Rule | Endpoint | Methods | Roles | Description |\n")
        f.write("| --- | --- | --- | --- | --- |\n")
        for r in routes_info:
            methods_str = ", ".join(r['methods'])
            roles_str = ", ".join(r['roles'])
            f.write(f"| `{r['rule']}` | `{r['endpoint']}` | `{methods_str}` | `{roles_str}` | {r['doc']} |\n")
            
    print(f"Scanned {len(routes_info)} routes successfully and saved to scratch/detected_routes.md")

if __name__ == '__main__':
    scan()
