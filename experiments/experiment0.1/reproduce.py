#!/usr/bin/env python3
"""Default: mock-only experiment0.1. Explicit --real-run permits paid inference."""
import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]/'src'))
from prompt_policy_llm import shopping_memory as sm

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, help='Offline replay/validation of an existing output directory')
    args, rest = parser.parse_known_args()
    if args.audit:
        if rest:
            parser.error('--audit does not accept inference arguments')
        import json
        print(json.dumps(sm.audit_run(args.audit), indent=2))
    else:
        sys.argv = [sys.argv[0], '--config', str(HERE/'config.json'), *rest]
        sm.main()
