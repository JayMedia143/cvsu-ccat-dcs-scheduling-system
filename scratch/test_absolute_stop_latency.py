import os
import time
import threading
from genetic_algorithm import GeneticScheduler, AlgorithmStopException

def run_test():
    print("Initializing GA Engine...")
    # Instantiate with minimal hardware requirements
    ga = GeneticScheduler([], [], [], [], [], {})
    ga.is_running = True
    ga.force_stop = False
    
    # Let's mock a signature file path
    ga.sig_path = "ga_stop.signal"
    if os.path.exists(ga.sig_path):
        os.remove(ga.sig_path)
        
    print("Testing absolute memory-based kill-switch (stop_engine)...")
    t0 = time.time()
    
    # We will start a separate thread that calls stop_engine after 0.5s
    def trigger_stop():
        time.sleep(0.5)
        print("🕒 [Thread] Triggering stop_engine()...")
        ga.stop_engine()
        
    th = threading.Thread(target=trigger_stop)
    th.start()
    
    # Simulate a loop inside _exhaustive_place_gene or repair
    print("Running simulated genetic loop...")
    stop_detected = False
    try:
        for idx in range(100000):
            # Simulated DSatur Repair loop index
            if ga.force_stop:
                raise AlgorithmStopException("Stop in repair.")
                
            # Simulated Phase 1/2 starts
            for s_idx in range(100):
                if s_idx % 5 == 0 and ga.force_stop:
                    raise AlgorithmStopException("Stop in exhaustive inner.")
            
            # Tiny sleep to simulate work
            time.sleep(0.001)
            
    except AlgorithmStopException as e:
        latency = (time.time() - t0) - 0.5
        print(f"✅ Success! Exception raised successfully: '{e}'")
        print(f"📊 Measured Latency: {latency*1000:.2f}ms")
        stop_detected = True
        
    th.join()
    assert stop_detected, "Error: Engine did not stop!"
    print("Engine absolute stop test passed with flying colors! 🌟")

if __name__ == '__main__':
    run_test()
