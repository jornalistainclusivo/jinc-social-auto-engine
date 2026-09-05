import json
import subprocess
import sys

REPO = "jornalistainclusivo/jinc-social-auto-engine"
BRANCH = "main"
API_ENDPOINT = f"repos/{REPO}/branches/{BRANCH}/protection"

BACKUP_FILE = "branch_protection_backup.json"

INTENDED_CONFIG = {
    "required_status_checks": {"strict": True, "contexts": ["lint-and-test"]},
    "enforce_admins": True,
    "required_pull_request_reviews": {
        "dismissal_restrictions": {"users": [], "teams": []},
        "dismiss_stale_reviews": False,
        "require_code_owner_reviews": False,
        "required_approving_review_count": 1,
    },
    "restrictions": None,
    "allow_force_pushes": False,
    "allow_deletions": False,
}


def run_gh_api(method, endpoint, payload=None, allow_404=False):
    cmd = ["gh", "api", "-X", method, endpoint]
    if payload is not None:
        cmd.extend(["--input", "-"])

    try:
        input_data = json.dumps(payload).encode("utf-8") if payload else None
        result = subprocess.run(cmd, input=input_data, capture_output=True, check=False)

        if result.returncode != 0:
            err = result.stderr.decode("utf-8")
            if allow_404 and "HTTP 404" in err:
                return None
            print(f"Error running gh api {method} {endpoint}:\n{err}")
            sys.exit(1)

        return json.loads(result.stdout.decode("utf-8"))
    except Exception as e:
        print(f"Exception calling gh api: {e}")
        sys.exit(1)


def inspect_current():
    print("INSPECT: Querying current branch protection...")
    current = run_gh_api("GET", API_ENDPOINT, allow_404=True)
    if current is None:
        print("INSPECT: No branch protection currently exists.")
        return {}
    return current


def compare_state(current):
    print("COMPARE: Analyzing delta between current and intended state...")

    # Simple dictionary check for idempotence (ignoring extra fields GH might return)
    # If the required fields exist and match, we are good.
    needs_update = False

    # Check required status checks
    curr_checks = current.get("required_status_checks", {})
    if not curr_checks:
        needs_update = True
    else:
        if (
            curr_checks.get("strict")
            != INTENDED_CONFIG["required_status_checks"]["strict"]
        ):
            needs_update = True
        curr_contexts = curr_checks.get("contexts", [])
        if sorted(curr_contexts) != sorted(
            INTENDED_CONFIG["required_status_checks"]["contexts"]
        ):
            needs_update = True

    # Check enforce_admins
    curr_admins = current.get("enforce_admins", {}).get("enabled", False)
    if curr_admins != INTENDED_CONFIG["enforce_admins"]:
        needs_update = True

    # Check required_pull_request_reviews
    curr_pr = current.get("required_pull_request_reviews", {})
    if not curr_pr:
        needs_update = True
    else:
        if (
            curr_pr.get("required_approving_review_count")
            != INTENDED_CONFIG["required_pull_request_reviews"][
                "required_approving_review_count"
            ]
        ):
            needs_update = True

    # Check allow_force_pushes
    if (
        current.get("allow_force_pushes", {}).get("enabled", False)
        != INTENDED_CONFIG["allow_force_pushes"]
    ):
        needs_update = True

    # Check allow_deletions
    if (
        current.get("allow_deletions", {}).get("enabled", False)
        != INTENDED_CONFIG["allow_deletions"]
    ):
        needs_update = True

    return needs_update


def apply_changes(current, needs_update):
    if not needs_update:
        print(
            "APPLY: Configuration is already correct. "
            "No changes needed. (Idempotent success)"
        )
        return

    print("APPLY: Changes needed. Saving backup...")
    with open(BACKUP_FILE, "w") as f:
        json.dump(current, f, indent=2)
    print(f"APPLY: Backup saved to {BACKUP_FILE}")

    print("APPLY: Applying intended branch protection rules...")
    run_gh_api("PUT", API_ENDPOINT, payload=INTENDED_CONFIG)
    print("APPLY: Configuration successfully applied.")


def verify():
    print("VERIFY: Confirming effective configuration matches intended state...")
    current = run_gh_api("GET", API_ENDPOINT)

    # Verify strict
    if not current.get("required_status_checks", {}).get("strict"):
        print("VERIFY ERROR: strict status checks not enabled.")
        sys.exit(1)

    # Verify contexts
    contexts = current.get("required_status_checks", {}).get("contexts", [])
    if "lint-and-test" not in contexts:
        print(
            f"VERIFY ERROR: required status checks contexts mismatch. Got: {contexts}"
        )
        sys.exit(1)

    # Verify enforce_admins
    if not current.get("enforce_admins", {}).get("enabled"):
        print("VERIFY ERROR: enforce_admins not enabled.")
        sys.exit(1)

    # Verify reviews
    if (
        current.get("required_pull_request_reviews", {}).get(
            "required_approving_review_count"
        )
        != 1
    ):
        print("VERIFY ERROR: required_approving_review_count mismatch.")
        sys.exit(1)

    # Verify force pushes
    if current.get("allow_force_pushes", {}).get("enabled", True):
        print("VERIFY ERROR: force pushes are allowed!")
        sys.exit(1)

    print("VERIFY: All assertions passed. Branch protection is strictly enforced.")


def main():
    print("Starting Branch Protection Governance Enforcement")
    current = inspect_current()
    needs_update = compare_state(current)
    apply_changes(current, needs_update)
    verify()
    print("Process completed safely.")


if __name__ == "__main__":
    main()
