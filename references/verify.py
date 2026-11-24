#!/usr/bin/env python3
"""Verify the standalone reference and scientific-claim companion records.

Default operation is read-only. Use --write after an intentional manuscript
edit to refresh citation locations and derived summaries. Recorded reading
scopes and access limitations are never rewritten by this command.
"""
from __future__ import annotations

import argparse
import json
import sys

sys.dont_write_bytecode = True
import claims
import metadata
import refresh


def verify(write=False):
    if not refresh.PAPER.is_dir():
        # Standalone repository: the manuscript sources (../paper/) are not
        # distributed here, so only the paper-independent reconciliation runs.
        if write:
            raise SystemExit('--write requires the manuscript sources in ../paper/')
        evidence = claims.verify(False)
        return {'status': 'PASS', 'manuscript_checks': 'SKIPPED',
                'reason': f'manuscript sources not found at {refresh.PAPER}; bibliography and '
                          'citation-location checks need ../paper/ next to this repository',
                'scientific_data_reconciled': [key for key in evidence if key not in {'status', 'scope'}],
                'operation': 'read-only verification'}
    identities = metadata.verify(write)
    evidence = claims.verify(write)
    citations = refresh.verify(write)
    return {'status': 'PASS', 'bibliography': identities,
            'citations_and_claims': citations,
            'scientific_data_reconciled': [key for key in evidence if key not in {'status', 'scope'}],
            'operation': 'explicit refresh' if write else 'read-only verification'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    print(json.dumps(verify(args.write), indent=2))


if __name__ == '__main__':
    main()
