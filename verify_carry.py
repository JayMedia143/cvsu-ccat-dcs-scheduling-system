# Verify with course code carry forward

import re

raw_text = """
AMBIL, KYLE ANGELO	COSC 60	Digital Logic and Design	2	1	2	3	BSCS 201 A,B,C,D	1	4	20
	ITEC 85	Information Assurance and Security I	2	1	2	3	BSINFOTECH 301 - A,B,C,D	1	4	20
								2	8	40
BAUTISTA, RENATO A.	DCIT 50	Object Oriented Programming	2	1	2	3	BSCS 201 A,B,C,D	1	4	20
		Object Oriented Programming	2	1	2	3	BSINFOTECH 201 A,B,C	1	3	15
	ITEC 200B	Capstone Project and Research 2	3	0	3	0	BSINFOTECH 401 - A,B	1	2	6
								3	9	41
CABRIDO, ALYANA	COSC 75	Software Engineering II	2	1	2	3	BSCS 301 - A,B,C,D,E	1	5	25
	ITEC 110	System Administration and Maintenance	2	1	2	3	BSINFOTECH 401 - A,B,C	1	3	15
								2	8	40
CEDILLO, CEDRICK KENN	ITEC 80	Human Computer Interaction	2	1	2	3	BSCS 401 - A,B,C	1	3	15
	ITEC 80	Introduction to Human Computer Interaction	2	1	2	3	BSINFOTECH 301 - A,B,C,D,E	1	5	25
								2	8	40
CLARITO, Angela C.	DCIT 24	Information Management	2	1	2	3	BSINFOTECH 201 A,B,C	1	3	15
	DCIT 24	Information Management	2	1	2	3	BSCS 201 A,B,C,D	1	4	20
	ICT 11	Empowerment Technologies (E-Tech: ICT for Professional Track	4	0	4	0	Grade 11	1	1	4
								3	8	39
CRUZ, JANESSA MARIELLE S.	COSC 101	Computer Graphics and Visual Computing	2	1	2	3	BSCS 301 - A,B,C,D,E	1	5	25
	ITEC 55	Platform Technologies	2	1	2	3	BSINFOTECH 202 - A,B,C	1	3	15
								2	8	40
ESTONILO, CHRISTOPHER G.	DCIT 60	Methods of Research	3	0	3	0	BSINFOTECH 301 - C	1	1	3
	COSC 200A	Undergraduate Thesis I	3	0	3	0	BSCS 401 - A	1	1	3
								2	2	6
GELERA, ARIES M.	DCIT 60	Methods of Research	3	0	3	0	BSINFOTECH 301 - B	1	1	3
	COSC 200A	Undergraduate Thesis I	3	0	3	0	BSCS 401 - C	1	1	3
								2	2	6
MELITANTE, GIRLIE P.	DCIT 21	Introduction to Computing	2	1	2	3	BSCS 101 - B,C	1	2	10
	INSY 50	Fundamentals of Information Systems	3	0	3	0	BSCS 201 A,B,C,D	1	4	12
	BSHM 23	Applied Business Tools and Technologies	2	1	2	3	BSHM 201 - D,E,F	1	3	15
	CvSU 101	Institutional Orientation	1	0	1	0	BSINFOTECH 101 - A,B,C	1	3	3
								4	12	40
MUYOT, ALLEN JOHN C.	DCIT 22	Computer Programming I	1	2	1	6	BSCS 101 - A,B	1	2	14
								1	2	14
NABABLIT, KARLO JOSE E.	DCIT 60	Methods of Research	3	0	3	0	BSINFOTECH 301 - A	1	1	3
	COSC 200A	Undergraduate Thesis I	3	0	3	0	BSCS 401 - B	1	1	3
								2	2	6
NOCON, YVANA JARDINE R.	INSY 55	System Analysis and Design	2	1	2	3	BSINFOTECH 301 - A,B,C	1	3	15
								1	3	15
OBON, ANA MARIE C.	DCIT 65	Social and Professional Issues	3	0	3	0	BSINFOTECH 401 A,B,C	1	3	9
	TLEP 08	Teaching Common Competencies in ICT	3	0	3	0	BTVTED 301 - A,B	1	2	6
								2	5	15
PELIÑA, MARY ANN E.	DCIT 60	Methods of Research	3	0	3	0	BSINFOTECH 301 - D,E	1	2	6
	ITEC 200B	Capstone Project and Research 2	3	0	3	0	BSINFOTECH 401 - C	1	1	3
								2	3	9
PERNALA, JOHN CHRISTIAN	COSC 50	Discreet Structures I	3	0	3	0	BSCS 101 A,B,C	1	3	9
	DCIT 22	Computer Programming I	1	2	1	6	BSCS 101 - C	1	1	7
	DCIT 22	Computer Programming I	1	2	1	6	BSINFOTECH 101 A,B,C	1	3	21
								3	7	37
SILVANO, MARY GRACE P.	DCIT 21	Introduction to Computing	2	1	2	3	BSINFOTECH 101 - A,B,C	1	3	15
	DCIT 21	Introduction to Computing	2	1	2	3	BSCS 101 - A	1	1	5
	BSHM 23	Applied Business Tools and Technologies	2	1	2	3	BSHM 201 - A,B,C	1	3	15
	CvSU 101	Institutional Orientation	1	0	1	0	BSCS 101 - A,B,C	1	3	3
								4	10	38
TINAMBACAN, AARON 	DCIT 26	Application Development and Emerging Technologies	2	1	2	3	BSCS 301 - A,B,C,D,E	1	5	25
	DCIT 26	Application Development and Emerging Technologies	2	1	2	3	BSINFOTECH 301 - A,B,C	1	3	15
								2	8	40
VILLANUEVA, LESTER D.	ITEC 90	Network Fundamentals	2	1	2	3	BSINFOTECH 301 - A,B,C	1	3	15
								1	3	15
DCS Teacher A (IT)	ITEC 111	Integrated Programming and Gtechnologies 2	2	1	2	3	BSINFOTECH 401 - A,B,C	1	3	15
	COSC 80	Operating Systems	2	1	2	3	BSCS 301 - A, B, C, D, E	1	5	25
								2	8	40
DCS Teacher B (CS)	COSC 105	Intelligence Systems	2	1	2	3	BSCS 401 - A, B, C	1	3	15
	TLE 3	Technology and Livelihood	4	0	4	0	Grade 9	1	1	4
	TLE 4	ICT Skills and Development	4	0	4	0	Grade 10	1	1	4
	ITEC 116	Systems Integration and Architecture 2	2	1	2	3	BSINFOTECH 401 - A,B,C	1	3	15
								1	8	38
DCS Teacher C (CS)	COSC 55	Discreet Structures II	3	0	3	0	BSCS 201 A,B,C,D	1	4	12
	INSY 55	System Analysis and Design	2	1	2	3	BSINFOTECH 301 - D,E	1	2	10
	COSC 111	Internet of Things	2	1	2	3	BSCS 401 - A,B,C	1	3	15
								3	9	37
DCS Teacher D (CS)	DCIT 26	Application Development and Emerging Technologies	2	1	2	3	BSINFOTECH 301 - D,E	1	2	10
	DCIT 65	Social and Professional Issues	3	0	3	0	BSCS 301 - A,B,C,D,E	1	5	15
	COSC 100	Automata Theory and Formal Languages	3	0	3	0	BSCS 401 - A,B,C	1	3	9
								3	10	34
CATALAN, RACQUEL A.	COSC 50	Discreet Structure	3	0	3	0	BSINFOTECH 101 A,B,C	1	3	9
								1	3	9
TOLEDO, IVAN	ITEC 85	Information Assurance and Security I	2	1	2	3	BSINFOTECH 301 - E	1	1	5
	COSC 85	Networks and Communication	2	1	2	3	BSCS 301 - C	1	1	5
								2	2	10
ORDOÑA, KARL VINCENT M.	ITEC 90	Network Fundamentals	2	1	2	3	BSINFOTECH 301 - D,E	1	2	10
								1	2	10
DCS Teacher E (DON) - IT	COSC 85	Networks and Communication	2	1	2	3	BSCS 301 - D,E	1	2	10
								1	2	10
DCS Teacher F (JM) - IT	COSC 85	Networks and Communication	2	1	2	3	BSCS 301 - A,B	1	2	10
								1	2	10
"""

def parse_sections(sec_str):
    sec_str = sec_str.replace('BSINFOTECH', 'BSIT').replace(' - ', ' ').strip()
    if ',' in sec_str:
        parts = [p.strip() for p in sec_str.split(',')]
        first = parts[0]
        base_match = re.match(r'^([A-Z0-9\s]+?)\s+([A-F])$', first)
        if base_match:
            base = base_match.group(1).strip()
            res = [first]
            for letter in parts[1:]:
                res.append(f"{base} {letter}")
            return res
        else:
            return parts
    return [sec_str]

parsed = []
current_faculty = ""
current_code = ""

for idx, line in enumerate(raw_text.split('\n')):
    line = line.strip('\r')
    if not line.strip():
        continue
    if "TOTAL CONTACT" in line or "Lec\tLab" in line or "Lec	Lab" in line or "Prepared by:" in line or "PART-TIMERS" in line:
        continue
    
    parts = line.split('\t')
    if len(parts) < 8:
        continue
    
    fac_name = parts[0].strip()
    if not fac_name:
        fac_name = current_faculty
    else:
        current_faculty = fac_name
        
    code = parts[1].strip()
    desc = parts[2].strip()
    
    if not desc:
        continue # skip summary rows
        
    if not code:
        code = current_code
    else:
        current_code = code
        
    try:
        lec_u = int(parts[3].strip() or 0)
        lab_u = int(parts[4].strip() or 0)
        lec_h = int(parts[5].strip() or 0)
        lab_h = int(parts[6].strip() or 0)
    except ValueError:
        continue
        
    sec_str = parts[7].strip()
    sections = parse_sections(sec_str)
    parsed.append((fac_name, code, desc, lec_u, lab_u, lec_h, lab_h, sections))

print(f"Parsed count: {len(parsed)}")

# Final verified loadings
LOADINGS = [
    ('AMBIL, KYLE ANGELO', 'COSC 60', 'Digital Logic and Design', 2, 1, 2, 3, ['BSCS 201 A', 'BSCS 201 B', 'BSCS 201 C', 'BSCS 201 D']),
    ('AMBIL, KYLE ANGELO', 'ITEC 85', 'Information Assurance and Security I', 2, 1, 2, 3, ['BSIT 301 A', 'BSIT 301 B', 'BSIT 301 C', 'BSIT 301 D']),
    ('BAUTISTA, RENATO A.', 'DCIT 50', 'Object Oriented Programming', 2, 1, 2, 3, ['BSCS 201 A', 'BSCS 201 B', 'BSCS 201 C', 'BSCS 201 D']),
    ('BAUTISTA, RENATO A.', 'DCIT 50', 'Object Oriented Programming', 2, 1, 2, 3, ['BSIT 201 A', 'BSIT 201 B', 'BSIT 201 C']),
    ('BAUTISTA, RENATO A.', 'ITEC 200B', 'Capstone Project and Research 2', 3, 0, 3, 0, ['BSIT 401 A', 'BSIT 401 B']),
    ('CABRIDO, ALYANA', 'COSC 75', 'Software Engineering II', 2, 1, 2, 3, ['BSCS 301 A', 'BSCS 301 B', 'BSCS 301 C', 'BSCS 301 D', 'BSCS 301 E']),
    ('CABRIDO, ALYANA', 'ITEC 110', 'System Administration and Maintenance', 2, 1, 2, 3, ['BSIT 401 A', 'BSIT 401 B', 'BSIT 401 C']),
    ('CEDILLO, CEDRICK KENN', 'ITEC 80', 'Human Computer Interaction', 2, 1, 2, 3, ['BSCS 401 A', 'BSCS 401 B', 'BSCS 401 C']),
    ('CEDILLO, CEDRICK KENN', 'ITEC 80', 'Introduction to Human Computer Interaction', 2, 1, 2, 3, ['BSIT 301 A', 'BSIT 301 B', 'BSIT 301 C', 'BSIT 301 D', 'BSIT 301 E']),
    ('CLARITO, ANGELA C.', 'DCIT 24', 'Information Management', 2, 1, 2, 3, ['BSIT 201 A', 'BSIT 201 B', 'BSIT 201 C']),
    ('CLARITO, ANGELA C.', 'DCIT 24', 'Information Management', 2, 1, 2, 3, ['BSCS 201 A', 'BSCS 201 B', 'BSCS 201 C', 'BSCS 201 D']),
    ('CLARITO, ANGELA C.', 'ICT 11', 'Empowerment Technologies (E-Tech: ICT for Professional Track', 4, 0, 4, 0, ['Grade 11']),
    ('CRUZ, JANESSA MARIELLE S.', 'COSC 101', 'Computer Graphics and Visual Computing', 2, 1, 2, 3, ['BSCS 301 A', 'BSCS 301 B', 'BSCS 301 C', 'BSCS 301 D', 'BSCS 301 E']),
    ('CRUZ, JANESSA MARIELLE S.', 'ITEC 55', 'Platform Technologies', 2, 1, 2, 3, ['BSIT 202 A', 'BSIT 202 B', 'BSIT 202 C']),
    ('ESTONILO, CHRISTOPHER G.', 'DCIT 60', 'Methods of Research', 3, 0, 3, 0, ['BSIT 301 C']),
    ('ESTONILO, CHRISTOPHER G.', 'COSC 200A', 'Undergraduate Thesis I', 3, 0, 3, 0, ['BSCS 401 A']),
    ('GELERA, ARIES M.', 'DCIT 60', 'Methods of Research', 3, 0, 3, 0, ['BSIT 301 B']),
    ('GELERA, ARIES M.', 'COSC 200A', 'Undergraduate Thesis I', 3, 0, 3, 0, ['BSCS 401 C']),
    ('MELITANTE, GIRLIE P.', 'DCIT 21', 'Introduction to Computing', 2, 1, 2, 3, ['BSCS 101 B', 'BSCS 101 C']),
    ('MELITANTE, GIRLIE P.', 'INSY 50', 'Fundamentals of Information Systems', 3, 0, 3, 0, ['BSCS 201 A', 'BSCS 201 B', 'BSCS 201 C', 'BSCS 201 D']),
    ('MELITANTE, GIRLIE P.', 'BSHM 23', 'Applied Business Tools and Technologies', 2, 1, 2, 3, ['BSHM 201 D', 'BSHM 201 E', 'BSHM 201 F']),
    ('MELITANTE, GIRLIE P.', 'CvSU 101', 'Institutional Orientation', 1, 0, 1, 0, ['BSIT 101 A', 'BSIT 101 B', 'BSIT 101 C']),
    ('MUYOT, ALLEN JOHN C.', 'DCIT 22', 'Computer Programming I', 1, 2, 1, 6, ['BSCS 101 A', 'BSCS 101 B']),
    ('NABABLIT, KARLO JOSE E.', 'DCIT 60', 'Methods of Research', 3, 0, 3, 0, ['BSIT 301 A']),
    ('NABABLIT, KARLO JOSE E.', 'COSC 200A', 'Undergraduate Thesis I', 3, 0, 3, 0, ['BSCS 401 B']),
    ('NOCON, YVANA JARDINE R.', 'INSY 55', 'System Analysis and Design', 2, 1, 2, 3, ['BSIT 301 A', 'BSIT 301 B', 'BSIT 301 C']),
    ('OBON, ANA MARIE C.', 'DCIT 65', 'Social and Professional Issues', 3, 0, 3, 0, ['BSIT 401 A', 'BSIT 401 B', 'BSIT 401 C']),
    ('OBON, ANA MARIE C.', 'TLEP 08', 'Teaching Common Competencies in ICT', 3, 0, 3, 0, ['BTVTED 301 A', 'BTVTED 301 B']),
    ('PELIÑA, MARY ANN E.', 'DCIT 60', 'Methods of Research', 3, 0, 3, 0, ['BSIT 301 D', 'BSIT 301 E']),
    ('PELIÑA, MARY ANN E.', 'ITEC 200B', 'Capstone Project and Research 2', 3, 0, 3, 0, ['BSIT 401 C']),
    ('PERNALA, JOHN CHRISTIAN', 'COSC 50', 'Discreet Structures I', 3, 0, 3, 0, ['BSCS 101 A', 'BSCS 101 B', 'BSCS 101 C']),
    ('PERNALA, JOHN CHRISTIAN', 'DCIT 22', 'Computer Programming I', 1, 2, 1, 6, ['BSCS 101 C']),
    ('PERNALA, JOHN CHRISTIAN', 'DCIT 22', 'Computer Programming I', 1, 2, 1, 6, ['BSIT 101 A', 'BSIT 101 B', 'BSIT 101 C']),
    ('SILVANO, MARY GRACE P.', 'DCIT 21', 'Introduction to Computing', 2, 1, 2, 3, ['BSIT 101 A', 'BSIT 101 B', 'BSIT 101 C']),
    ('SILVANO, MARY GRACE P.', 'DCIT 21', 'Introduction to Computing', 2, 1, 2, 3, ['BSCS 101 A']),
    ('SILVANO, MARY GRACE P.', 'BSHM 23', 'Applied Business Tools and Technologies', 2, 1, 2, 3, ['BSHM 201 A', 'BSHM 201 B', 'BSHM 201 C']),
    ('SILVANO, MARY GRACE P.', 'CvSU 101', 'Institutional Orientation', 1, 0, 1, 0, ['BSCS 101 A', 'BSCS 101 B', 'BSCS 101 C']),
    ('TINAMBACAN, AARON', 'DCIT 26', 'Application Development and Emerging Technologies', 2, 1, 2, 3, ['BSCS 301 A', 'BSCS 301 B', 'BSCS 301 C', 'BSCS 301 D', 'BSCS 301 E']),
    ('TINAMBACAN, AARON', 'DCIT 26', 'Application Development and Emerging Technologies', 2, 1, 2, 3, ['BSIT 301 A', 'BSIT 301 B', 'BSIT 301 C']),
    ('VILLANUEVA, LESTER D.', 'ITEC 90', 'Network Fundamentals', 2, 1, 2, 3, ['BSIT 301 A', 'BSIT 301 B', 'BSIT 301 C']),
    ('DCS Teacher A (IT)', 'ITEC 111', 'Integrated Programming and Gtechnologies 2', 2, 1, 2, 3, ['BSIT 401 A', 'BSIT 401 B', 'BSIT 401 C']),
    ('DCS Teacher A (IT)', 'COSC 80', 'Operating Systems', 2, 1, 2, 3, ['BSCS 301 A', 'BSCS 301 B', 'BSCS 301 C', 'BSCS 301 D', 'BSCS 301 E']),
    ('DCS Teacher B (CS)', 'COSC 105', 'Intelligence Systems', 2, 1, 2, 3, ['BSCS 401 A', 'BSCS 401 B', 'BSCS 401 C']),
    ('DCS Teacher B (CS)', 'TLE 3', 'Technology and Livelihood', 4, 0, 4, 0, ['Grade 9']),
    ('DCS Teacher B (CS)', 'TLE 4', 'ICT Skills and Development', 4, 0, 4, 0, ['Grade 10']),
    ('DCS Teacher B (CS)', 'ITEC 116', 'Systems Integration and Architecture 2', 2, 1, 2, 3, ['BSIT 401 A', 'BSIT 401 B', 'BSIT 401 C']),
    ('DCS Teacher C (CS)', 'COSC 55', 'Discreet Structures II', 3, 0, 3, 0, ['BSCS 201 A', 'BSCS 201 B', 'BSCS 201 C', 'BSCS 201 D']),
    ('DCS Teacher C (CS)', 'INSY 55', 'System Analysis and Design', 2, 1, 2, 3, ['BSIT 301 D', 'BSIT 301 E']),
    ('DCS Teacher C (CS)', 'COSC 111', 'Internet of Things', 2, 1, 2, 3, ['BSCS 401 A', 'BSCS 401 B', 'BSCS 401 C']),
    ('DCS Teacher D (CS)', 'DCIT 26', 'Application Development and Emerging Technologies', 2, 1, 2, 3, ['BSIT 301 D', 'BSIT 301 E']),
    ('DCS Teacher D (CS)', 'DCIT 65', 'Social and Professional Issues', 3, 0, 3, 0, ['BSCS 301 A', 'BSCS 301 B', 'BSCS 301 C', 'BSCS 301 D', 'BSCS 301 E']),
    ('DCS Teacher D (CS)', 'COSC 100', 'Automata Theory and Formal Languages', 3, 0, 3, 0, ['BSCS 401 A', 'BSCS 401 B', 'BSCS 401 C']),
    ('CATALAN, RACQUEL A.', 'COSC 50', 'Discreet Structure', 3, 0, 3, 0, ['BSIT 101 A', 'BSIT 101 B', 'BSIT 101 C']),
    ('TOLEDO, IVAN', 'ITEC 85', 'Information Assurance and Security I', 2, 1, 2, 3, ['BSIT 301 E']),
    ('TOLEDO, IVAN', 'COSC 85', 'Networks and Communication', 2, 1, 2, 3, ['BSCS 301 C']),
    ('ORDOÑA, KARL VINCENT M.', 'ITEC 90', 'Network Fundamentals', 2, 1, 2, 3, ['BSIT 301 D', 'BSIT 301 E']),
    ('DCS Teacher E (DON) - IT', 'COSC 85', 'Networks and Communication', 2, 1, 2, 3, ['BSCS 301 D', 'BSCS 301 E']),
    ('DCS Teacher F (JM) - IT', 'COSC 85', 'Networks and Communication', 2, 1, 2, 3, ['BSCS 301 A', 'BSCS 301 B']),
]

mismatches = 0
for idx in range(max(len(parsed), len(LOADINGS))):
    if idx >= len(parsed):
        print(f"Row {idx+1} is missing in parsed (pasted) data! Expected: {LOADINGS[idx]}")
        mismatches += 1
        continue
    if idx >= len(LOADINGS):
        print(f"Row {idx+1} is extra in parsed (pasted) data! Found: {parsed[idx]}")
        mismatches += 1
        continue
        
    p = parsed[idx]
    l = LOADINGS[idx]
    
    diffs = []
    if p[0].upper() != l[0].upper():
        diffs.append(f"Faculty name: '{p[0]}' vs '{l[0]}'")
    if p[1].upper() != l[1].upper():
        diffs.append(f"Course code: '{p[1]}' vs '{l[1]}'")
    if p[2].upper() != l[2].upper():
        diffs.append(f"Course description: '{p[2]}' vs '{l[2]}'")
    if p[3] != l[3] or p[4] != l[4] or p[5] != l[5] or p[6] != l[6]:
        diffs.append(f"Units/Hours: ({p[3]},{p[4]},{p[5]},{p[6]}) vs ({l[3]},{l[4]},{l[5]},{l[6]})")
        
    p_set = {s.upper().replace(' ', '') for s in p[7]}
    l_set = {s.upper().replace(' ', '') for s in l[7]}
    if p_set != l_set:
        diffs.append(f"Sections: {p[7]} vs {l[7]}")
        
    if diffs:
        mismatches += 1
        print(f"Row {idx+1} has mismatch:")
        for d in diffs:
            print(f"  - {d}")

if mismatches == 0 and len(parsed) == len(LOADINGS):
    print("\n--- AMAZING! 100% PERFECT MATCH AND ZERO MISMATCHES! ---")
else:
    print(f"\nCompleted alignment check with {mismatches} mismatches. Parsed: {len(parsed)}, Reference: {len(LOADINGS)}")
