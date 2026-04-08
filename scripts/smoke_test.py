#!/usr/bin/env python3
"""
Lightweight smoke test for the active-development CLI.
Runs non-destructive commands to catch import/argparse/runtime regressions.
Treats 'Anki not running' as a warning, not a failure.
"""
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PY = BASE / ".venv312" / "bin" / "python3"
FLOW = BASE / "anki_flow.py"

TESTS = [
    [str(PY), str(FLOW), "--help"],
    [str(PY), str(FLOW), "audit"],
    [str(PY), str(FLOW), "sync"],
    [str(PY), str(FLOW), "known", "--mode", "learned"],
    [str(PY), str(FLOW), "sentences", "--help"],
    [str(PY), str(FLOW), "sentences", "known", "--mode", "learned"],
    [str(PY), str(FLOW), "build", "--dry-run", "--limit", "1"],
]


def main():
    print("Running smoke tests...\n")
    failures = 0
    for i, cmd in enumerate(TESTS, 1):
        label = " ".join(cmd[2:])
        print(f"[{i}/{len(TESTS)}] {label}")
        try:
            res = subprocess.run(cmd, cwd=str(BASE), capture_output=True, text=True, timeout=120)
            combined = ((res.stdout or "") + "\n" + (res.stderr or "")).strip()
            if res.returncode == 0:
                print("  PASS")
            elif "Cannot connect to Anki" in combined or "Could not reach AnkiConnect" in combined:
                print("  WARN (Anki not running)")
            else:
                failures += 1
                print("  FAIL")
                if res.stdout.strip():
                    print("  stdout:")
                    print("    " + res.stdout.strip().replace("\n", "\n    "))
                if res.stderr.strip():
                    print("  stderr:")
                    print("    " + res.stderr.strip().replace("\n", "\n    "))
        except Exception as e:
            failures += 1
            print(f"  ERROR: {e}")
        print()

    if failures:
        print(f"Smoke test complete: {failures} failure(s)")
        sys.exit(1)
    print("Smoke test complete: all checks passed")


if __name__ == "__main__":
    main()
