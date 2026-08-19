"""Regenerate the repo's OpenAPI snapshot (``routes.json``) from the app itself.

The snapshot is what mobile and desktop clients are written against, so a stale
one is worse than none: it looks authoritative while describing endpoints that
moved. The previous file carried 43 of 348 paths and predated every module added
since — including the whole mobile BFF.

No server is needed. ``api.app`` imports cleanly offline: its schema bootstraps
are already wrapped in try/except because the app is expected to start before a
database is reachable.

    backend/.venv/bin/python scripts/dump_openapi.py          # writes routes.json
    backend/.venv/bin/python scripts/dump_openapi.py --check  # CI: fail if stale

Written UTF-8. The old snapshot was UTF-16 (a PowerShell redirect artefact),
which ``json.load`` handles only via an explicit encoding argument.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_OUT = REPO_ROOT / 'routes.json'


def build_spec() -> dict:
    sys.path.insert(0, str(BACKEND_DIR))
    from api.app import app  # imported late: sys.path must be set first

    return app.openapi()


def render(spec: dict) -> str:
    # Sorted paths keep the diff readable when a single route changes; without
    # it a re-import can reshuffle the file and hide the real change.
    spec = dict(spec)
    spec['paths'] = dict(sorted(spec['paths'].items()))
    return json.dumps(spec, indent=2, ensure_ascii=False, sort_keys=False) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        '--check',
        action='store_true',
        help='exit 1 if the file on disk differs from the app',
    )
    args = parser.parse_args()

    rendered = render(build_spec())

    if args.check:
        if not args.out.exists():
            print(f'{args.out} is missing', file=sys.stderr)
            return 1
        if args.out.read_text(encoding='utf-8') != rendered:
            print(
                f'{args.out} is stale — run scripts/dump_openapi.py',
                file=sys.stderr,
            )
            return 1
        print(f'{args.out} is current')
        return 0

    args.out.write_text(rendered, encoding='utf-8')
    print(f'wrote {args.out} ({len(json.loads(rendered)["paths"])} paths)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
