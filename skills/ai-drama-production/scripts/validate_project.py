"""Validate a project and optional scoped-revision baseline; never modifies content."""
from pathlib import Path
import argparse
import json
import sys
from production_common import read_json, validate, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--only', nargs='+')
    parser.add_argument('--for-render', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    try:
        if args.only and not args.baseline: raise ValueError('--only必须与--baseline一起使用')
        report = validate(read_json(args.project), args.project,
                          read_json(args.baseline) if args.baseline else None, args.only, args.for_render)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report = {'status': 'failed', 'errors': [str(exc)], 'warnings': []}
    if args.report: write_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
