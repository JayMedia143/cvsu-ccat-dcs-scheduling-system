import re
import json
import os

def parse_manifest(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    manifest = []
    current_phase = None
    current_subphase = None
    current_base_url = "/"  # Default for Phase 0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Detect Phase (e.g. Phase 0: System Entry (login.html))
        phase_match = re.search(r'^##\s+Phase\s+(\d+):\s+(.*)', line)
        if phase_match:
            pid = int(phase_match.group(1))
            title = phase_match.group(2).strip()
            
            # Extract URL from parenthesis in header if present
            header_url_match = re.search(r'\((.*?)\)', title)
            if header_url_match:
                header_url = header_url_match.group(1).replace('.html', '')
                current_base_url = "/" + header_url if not header_url.startswith('/') else header_url
            else:
                # Fallback defaults
                if pid == 0: current_base_url = "/"
                elif pid == 1: current_base_url = "/dashboard"
                elif pid == 2: current_base_url = "/proposal_hub"
                elif pid == 3: current_base_url = "/manage_courses" # Default
                elif pid == 9: current_base_url = "/manage_users"

            current_phase = {
                "id": pid,
                "title": re.sub(r'\(.*?\)', '', title).strip(),
                "items": []
            }
            manifest.append(current_phase)
            current_subphase = None
            continue

        # Detect Subphase (e.g. 3.1 Course Management (manage_courses.html))
        subphase_match = re.search(r'^###\s+(\d+\.\d+)\s+(.*)', line)
        if subphase_match:
            subtitle = subphase_match.group(2).strip()
            current_subphase = re.sub(r'\(.*?\)', '', subtitle).strip()
            
            # Update base URL for this subphase
            url_match = re.search(r'\((.*?)\)', subtitle)
            if url_match:
                extracted = url_match.group(1).replace('.html', '')
                current_base_url = "/" + extracted if not extracted.startswith('/') else extracted
            else:
                # Heuristics if parenthesis missing
                low = subtitle.lower()
                if "course" in low: current_base_url = "/manage_courses"
                elif "section" in low: current_base_url = "/manage_sections"
                elif "student" in low: current_base_url = "/manage_students"
                elif "faculty" in low: current_base_url = "/manage_faculty"
                elif "room" in low: current_base_url = "/manage_rooms"
                elif "department" in low: current_base_url = "/manage_departments"
                elif "archive" in low: 
                    if "courses" in low: current_base_url = "/archives/courses"
                    elif "sections" in low: current_base_url = "/archives/sections"
                    else: current_base_url = "/archives/courses"
            continue

        # Detect Audit Item
        item_match = re.match(r'^-\s+\[\s*\]\s+(.*)', line)
        if item_match and current_phase:
            content = item_match.group(1).strip()
            
            # Deep-Automation Heuristic
            test_type = "manual"
            if "Logic:" in content or "Heartbeat" in content or "Tracker" in content or "Sanitization" in content:
                test_type = "logic"
            elif any(k in content for k in ["Button:", "Placeholder:", "Link:", "Card:", "Stat:", "Input:", "Select:", "Modal:", "Toast", "Progress"]):
                test_type = "auto"
            
            # Extract parenthetical description
            desc_match = re.search(r'\((.*?)\)', content)
            description = desc_match.group(1) if desc_match else ""
            
            # Name cleaning
            name = re.sub(r'\(.*?\)', '', content).strip()
            
            # Define target URL
            url = current_base_url
            if test_type == "logic":
                url = "/api/audit/logic_ping"
            
            # Specific micro-overrides (e.g. Generator page)
            if "Generator" in content: url = "/generate_schedule"
            elif "Constraints" in content: url = "/manage_constraints"
            elif "Recycle Bin" in content: 
                if "Course" in (current_subphase or ""): url = "/archives/courses"

            current_phase["items"].append({
                "subphase": current_subphase,
                "name": name,
                "description": description,
                "type": test_type,
                "url": url,
                "status": "pending"
            })

    return manifest

if __name__ == "__main__":
    manifest_path = r"c:\Users\Jaedon\.gemini\antigravity\brain\6eb0b5e6-917c-4b83-b2cd-baf05e4ee535\system_feature_audit.md"
    output_path = r"c:\WFH\jeremy\12. CvSU_Scheduling_System-Version-2.25_send\CvSU_Scheduling_System-Version-2 - antigravity_2_claude - Copy\static\json\audit_manifest.json"
    
    data = parse_manifest(manifest_path)
    
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    
    print(f"Manifest converted successfully to {output_path}")
