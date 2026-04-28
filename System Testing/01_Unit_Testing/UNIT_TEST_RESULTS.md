# 🛡️ Unit Testing Report

**Date Generated**: 2026-04-28
**Environment**: Python 3.11 / Pytest / Automated Test Reporter
**Thesis Reference**: Scheduling System v2

| Test Case ID | Test Description | Expected Result | Actual Result | Status |
| :--- | :--- | :--- | :--- | :--- |
| **TC-U1** | Detect faculty overlap | Conflict Detected (True) | Conflict Detected (True) | ✅ **PASSED** |
| **TC-U2** | Detect room overlap | Conflict Detected (True) | Conflict Detected (True) | ✅ **PASSED** |
| **TC-U3** | Detect section overlap | Conflict Detected (True) | Conflict Detected (True) | ✅ **PASSED** |
| **TC-U4** | Different days test | No Conflict (False) | No Conflict (False) | ✅ **PASSED** |
| **TC-U5** | Back-to-back test | No Conflict (False) | No Conflict (False) | ✅ **PASSED** |
| **TC-U6** | Room suitability check | Suitability Error | Suitability Error | ✅ **PASSED** |
| **TC-U7** | Consecutive hours limit | Violation Detected | Violation Detected | ✅ **PASSED** |
| **TC-U8** | Lec-Lab sequence rule | Sequence Error | Sequence Error | ✅ **PASSED** |
| **TC-U9** | Hour-to-Slot conversion | 6 Slots (3 Hrs) | 6 Slots (3 Hrs) | ✅ **PASSED** |
| **TC-U10** | Max weekly hours limit | Violation Detected | Violation Detected | ✅ **PASSED** |
| **TC-U11** | Preferred day restriction | Day Restriction Error | Day Restriction Error | ✅ **PASSED** |
| **TC-U12** | Room capacity validation | Capacity Error | Capacity Error | ✅ **PASSED** |
| **TC-U13** | Bitmask shifting accuracy | Bitmask 48 | Bitmask 48 | ✅ **PASSED** |
| **TC-U14** | Gene default initialization | Valid Defaults | Valid Defaults | ✅ **PASSED** |
| **TC-U15** | Population size check | Valid Size | Valid Size | ✅ **PASSED** |
| **TC-U16** | Min duration (1 slot) | Valid Slot | Valid Slot | ✅ **PASSED** |
| **TC-U17** | Max duration boundary | Valid Slots | Valid Slots | ✅ **PASSED** |
| **TC-U18** | Start of day boundary | Start Idx 0 | Start Idx 0 | ✅ **PASSED** |
| **TC-U19** | End of day boundary | Valid End Idx | Valid End Idx | ✅ **PASSED** |
| **TC-U20** | Fixed gene protection | No Mutation | No Mutation | ✅ **PASSED** |
| **TC-U21** | Identical crossover | Identical Offspring | Identical Offspring | ✅ **PASSED** |
| **TC-U22** | Zero conflict fitness | Score 1.0 | Score 1.0 | ✅ **PASSED** |
| **TC-U23** | Penalty weight scaling | Correct Multiplier | Correct Multiplier | ✅ **PASSED** |
| **TC-U24** | Empty schedule handling | No Crash | No Crash | ✅ **PASSED** |
| **TC-U25** | Duplicate gene check | Detection OK | Detection OK | ✅ **PASSED** |
| **TC-U26** | Same day Lec-Lab sequence | Valid Order | Valid Order | ✅ **PASSED** |
| **TC-U27** | Different day Lec-Lab | Valid Sequence | Valid Sequence | ✅ **PASSED** |
| **TC-U28** | Faculty multi-section collision | Conflict OK | Conflict OK | ✅ **PASSED** |
| **TC-U29** | Room multi-faculty collision | Conflict OK | Conflict OK | ✅ **PASSED** |
| **TC-U30** | Async duration validation | Valid Duration | Valid Duration | ✅ **PASSED** |

---
**Summary**: 30 out of 30 tests passed (100% logic accuracy).
