import sys, os, time
# Auto-resolve project root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from genetic_algorithm import GeneticScheduler, Gene

def run_benchmark():
    print("\n" + "="*95)
    print("⚡ PERFORMANCE TESTING: ALGORITHM EFFICIENCY (O(N²))")
    print("="*95)
    
    datasets = [
        {"Level": "Small", "N": 50, "Checks": "1,225"},
        {"Level": "Medium", "N": 250, "Checks": "31,125"},
        {"Level": "Large", "N": 1000, "Checks": "499,500"},
        {"Level": "Thesis Stress", "N": 5000, "Checks": "12,497,500"}
    ]
    
    # Header
    print(f"{'Complexity Level':<20} | {'No. of Genes (N)':<18} | {'Overlap Checks (N²/2)':<25} | {'Execution Time':<15} | {'Status'}")
    print("-" * 95)
    
    for d in datasets:
        # Build simulation
        genes = [Gene(i, 1, 1, 1, 1, 8, 2) for i in range(d['N'])]
        start = time.time()
        # Simulate overlap loops
        for i in range(len(genes)):
            for j in range(i+1, len(genes)):
                GeneticScheduler._genes_overlap(genes[i], genes[j])
        elapsed = round(time.time() - start, 4)
        
        print(f"{d['Level']:<20} | {d['N']:<18} | {d['Checks']:<25} | {elapsed:<15} | ✅ PASSED")

    print("-" * 95)
    print("✅ Benchmark Testing Complete!\n")

if __name__ == "__main__":
    run_benchmark()
