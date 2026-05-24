import subprocess
import sys
import os

def run_tests():
    print("="*70)
    print("🚀 INITIATING 11-LAYER MASTER TESTING MATRIX...")
    print("="*70)

    root_dir = os.path.dirname(os.path.abspath(__file__))

    # 1. Backend Matrix
    print("\n[1/2] RUNNING BACKEND TEST SUITE (Unit, API, Cron, Warm Boot, Chaos, Soak)...")
    backend_result = subprocess.run(
        [sys.executable, "-m", "pytest", "backend/tests", "-v"],
        cwd=root_dir
    )

    if backend_result.returncode != 0:
        print("\n❌ BACKEND TESTS FAILED! Aborting master test suite.")
        sys.exit(backend_result.returncode)

    print("\n✅ BACKEND TESTS PASSED SUCESSFULLY.")

    # 2. Frontend Matrix
    print("\n[2/2] RUNNING FRONTEND TEST SUITE (Playwright UI & E2E)...")
    frontend_dir = os.path.join(root_dir, "frontend")
    
    # Run playwright test
    frontend_result = subprocess.run(
        "npx playwright test",
        cwd=frontend_dir,
        shell=True
    )

    if frontend_result.returncode != 0:
        print("\n❌ FRONTEND TESTS FAILED! Aborting master test suite.")
        sys.exit(frontend_result.returncode)

    print("\n✅ FRONTEND TESTS PASSED SUCESSFULLY.")

    # 3. Success Ascii Art
    print("\n")
    print(r"""
       __   __    __       __ __   __   ___  ___  ___  __  ___  __ 
      / /\ | |   | |      /__/ | \/ |  |__  |__   |  |__  |  \ |__)
     /_/--\|_|__ |_|__    __/\ |    |  |___ |     |  |___ |__/ |  \
                                                                    
            __   ___  __       __  ___     __   ___  __   __       
           |  \ |__  |__) |   /  \  |     |__) |__  |__| |  \ \ /  
           |__/ |___ |    |__ \__/  |     |  \ |___ |  | |__/  |   
    """)
    print("="*70)
    print("                 ALL SYSTEMS GO - DEPLOYMENT READY                 ")
    print("="*70)

if __name__ == "__main__":
    run_tests()
