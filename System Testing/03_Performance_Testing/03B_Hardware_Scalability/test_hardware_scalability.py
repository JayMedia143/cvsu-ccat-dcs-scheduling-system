import os
import sys

def compute_thesis_score(cpu_count, cpu_mhz, gpu_name="None", sm_count=0, major=0, minor=0):
    # --- THESIS FORMULA ---
    cpu_score = cpu_count * (cpu_mhz / 1000)
    gpu_score = 0
    if "NVIDIA" in gpu_name:
        gpu_score = sm_count * (major + (minor / 10))
    total_score = cpu_score + (gpu_score * 2)
    return round(cpu_score, 1), round(gpu_score, 1), round(total_score, 1)

def run_hardware_predictor():
    print("\n" + "="*105)
    print("🧬 GENETIC ALGORITHM PERFORMANCE ANALYSIS (GENERATION-BASED COMPUTATION)")
    print("="*105)
    
    # Constants for DCS Scale (Seeder 10)
    total_generations = 24000
    gps_multiplier = 2.08  # GPS per Score point (Based on 100 GPS for Score 48)
    
    tiers = [
        {"name": "High-End",    "cpu_m": "i7-1065G7", "cpu_c": 8, "mhz": 1500, "gpu": "NVIDIA GTX 1660 Ti", "sm": 24, "maj": 7, "min": 5},
        {"name": "Mid-Range",   "cpu_m": "i7-860",    "cpu_c": 8, "mhz": 2800, "gpu": "AMD Radeon HD 5700", "sm": 0,  "maj": 0, "min": 0},
        {"name": "Low-End",     "cpu_m": "i5-4310M",  "cpu_c": 4, "mhz": 2700, "gpu": "Intel HD 4600",      "sm": 0,  "maj": 0, "min": 0},
        {"name": "Entry-Level", "cpu_m": "i3-1005G1", "cpu_c": 4, "mhz": 1200, "gpu": "Intel UHD Graphics", "sm": 0,  "maj": 0, "min": 0}
    ]

    print(f"📊 COMPUTATION PARAMETERS:")
    print(f"   - Target Generations: {total_generations:,} rounds")
    print(f"   - GPS Formula: Total_Score * {gps_multiplier} (Generations Per Second)")
    print(f"   - Expected Time: (Generations / GPS) / 60")
    print("-" * 105)

    # Generate Comparison Table
    header = f"{'HARDWARE TIER':<15} | {'TOTAL SCORE':<12} | {'EST. GPS':<12} | {'EXPECTED TIME (MIN)'}"
    print(header)
    print("-" * 105)
    
    for t in tiers:
        _, _, total = compute_thesis_score(t['cpu_c'], t['mhz'], t['gpu'], t['sm'], t['maj'], t['min'])
        
        # Calculate GPS and Time
        est_gps = round(total * gps_multiplier, 1)
        # Avoid division by zero
        expected_min = round((total_generations / est_gps) / 60, 2) if est_gps > 0 else 0
        
        print(f"{t['name']:<15} | {total:<12} | {est_gps:<12} | {expected_min} mins")
        
    print("="*105)
    print("\n✅ Calculation Finalized! (Terminal Output Only - No MD changes)")

if __name__ == "__main__":
    run_hardware_predictor()
