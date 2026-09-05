import subprocess
import sys

def run_cmd(cmd, exit_on_fail=True):
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FAILED: {' '.join(cmd)}")
        print(result.stdout)
        print(result.stderr)
        if exit_on_fail:
            sys.exit(result.returncode)
    else:
        print("OK\n")
    return result.stdout.strip()

def main():
    print("=== SDLC Governance Verification Checklist ===\n")
    
    # 1. Check branch
    branch = run_cmd(["git", "branch", "--show-current"], exit_on_fail=False)
    if branch == "main":
        print("ERROR: You are on the 'main' branch. Direct work on 'main' is forbidden.")
        sys.exit(1)
        
    # 2. Run formatting check
    run_cmd(["ruff", "format", "--check", "."])
    
    # 3. Run linter
    run_cmd(["ruff", "check", "."])
    
    # 4. Run tests
    print("Running: pytest")
    result = subprocess.run(["pytest"], capture_output=True, text=True)
    if result.returncode not in [0, 5]: # 5 is NO TESTS
        print(f"FAILED: pytest")
        print(result.stdout)
        print(result.stderr)
        sys.exit(result.returncode)
    else:
        print("OK\n")
        
    print("==============================================")
    print("ALL TECHNICAL CHECKS PASSED.")
    print("\nGOVERNANCE NOTICE:")
    print("This checklist is strictly a VERIFICATION MECHANISM, not an AUTHORIZATION MECHANISM.")
    print("Required PR Approval is a GitHub governance control, but it does NOT constitute Human Gate authorization.")
    print("The Human Gate remains a separate, explicit human authorization boundary.")
    print("==============================================")

if __name__ == "__main__":
    main()
