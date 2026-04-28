# ⚡ Performance Testing Report (GA Complexity)

**Date Generated**: 2026-04-28
**Environment**: Python 3.11 / Core Benchmarker
**Thesis Reference**: Scheduling System v2

| Complexity Level | No. of Genes (N) | Overlap Checks (N²/2) | Execution Time | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Small** | 50 | 1,225 | 0.0s | ✅ PASSED |
| **Medium** | 250 | 31,125 | 0.01s | ✅ PASSED |
| **Large** | 1000 | 499,500 | 0.1885s | ✅ PASSED |
| **Thesis Stress** | 5000 | 12,497,500 | 4.1742s | ✅ PASSED |

---
**Technical Analysis**:
1. **Computational Complexity**: The core overlap detection logic follows **O(N²)** complexity.
2. **Efficiency**: The system can handle up to 1,000 genes (Large) in sub-second time, ensuring fast fitness evaluation during the GA process.
3. **Scalability**: Even at Stress levels (5,000 genes), the logic remains stable, proving the robustness of the `_genes_overlap` implementation.
