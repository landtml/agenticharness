"""Command line: judge a workspace against a contract.

    python -m urh_gate check --contract path/to/contract.py --workspace DIR [--claimed done]

Prints the verdict as JSON. Exit code: 0 pass, 1 fail, 2 park, 3 usage error.
"""

import argparse
import json
import sys

from .contract import load_contract
from .gate import FAIL, PARK, PASS, Gate


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m urh_gate")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="judge one workspace")
    c.add_argument("--contract", required=True)
    c.add_argument("--workspace", required=True)
    c.add_argument("--claimed", help="the worker's self-report; recorded, never consulted")
    c.add_argument("--repair-note", action="store_true", help="print the repair note instead of JSON")
    args = ap.parse_args(argv)
    verdict = Gate(load_contract(args.contract)).evaluate(args.workspace, claimed=args.claimed)
    if args.repair_note:
        print(verdict.repair_note() or "pass")
    else:
        print(json.dumps(verdict.to_json(), indent=1))
    return {PASS: 0, FAIL: 1, PARK: 2}[verdict.status]


if __name__ == "__main__":
    sys.exit(main())
