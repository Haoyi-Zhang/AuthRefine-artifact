"""Validate the public repository layout without executing research experiments."""
from __future__ import annotations

import ast
import importlib.util
import json
import os
from pathlib import Path
import re


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    errors: list[str] = []
    warnings: list[str] = []
    ignored = {'.git', '__pycache__', '.pytest_cache', '.venv', 'venv', 'node_modules'}

    readme = root / os.environ.get('README_ENTRY', 'README.md')
    if not readme.is_file() or not readme.read_text(encoding='utf-8-sig').strip():
        errors.append('Repository usage documentation is missing or empty.')

    required = (
        root / 'LICENSE', root / 'CITATION.cff', root / 'Makefile',
        root / 'evaluate.py', root / 'TESTING.md',
        root / 'test_environments.json',
    )
    for path in required:
        if not path.is_file():
            errors.append('Required repository file is missing: ' + path.relative_to(root).as_posix())

    forbidden_root = re.compile(r'(round|checkpoint|continuation|final|manifest.*sha)', re.I)
    for path in root.iterdir():
        if forbidden_root.search(path.name):
            errors.append('Delivery/review artifact remains at repository root: ' + path.name)

    forbidden_suffixes = ('.pre_file_capture', '.pyc', '.pyo', '~')
    source_count = 0
    private_path_pattern = re.compile(r'/(?:mnt/data|home/oai)/')
    credential_patterns = (
        re.compile(r'AKIA[0-9A-Z]{16}'),
        re.compile(r'gh[pousr]_[A-Za-z0-9_]{30,}'),
        re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    )
    text_suffixes = {'.py','.md','.txt','.tex','.json','.csv','.yml','.yaml','.toml','.cff','.conf'}
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root)
        if any(part in ignored for part in rel.parts):
            continue
        if path.is_dir():
            if path.name == '__pycache__':
                errors.append('Python cache directory is tracked: ' + rel.as_posix())
            continue
        if path.name.endswith(forbidden_suffixes):
            errors.append('Backup/cache file is tracked: ' + rel.as_posix())
        if path.is_symlink() and not path.resolve().is_relative_to(root):
            errors.append('Source symlink leaves the repository: ' + rel.as_posix())
            continue
        if path.suffix == '.py':
            try:
                ast.parse(path.read_bytes(), filename=rel.as_posix())
                source_count += 1
            except (SyntaxError, UnicodeError, OSError) as exc:
                errors.append(rel.as_posix() + ': ' + str(exc))
        if path.suffix.lower() in text_suffixes and path.stat().st_size <= 5_000_000:
            try:
                text = path.read_text(encoding='utf-8-sig')
            except (UnicodeError, OSError):
                continue
            # Generated raw scientific records may retain an original execution path;
            # public documentation and executable source must not expose one.
            if private_path_pattern.search(text) and not rel.as_posix().startswith('results/'):
                errors.append('Private absolute path in public source/documentation: ' + rel.as_posix())
            for pattern in credential_patterns:
                if pattern.search(text):
                    errors.append('Possible credential/private key in: ' + rel.as_posix())
                    break

    try:
        registry = json.loads((root/'test_environments.json').read_text())
        test_files = {f'tests.{p.stem}' for p in (root/'tests').glob('test_*.py')}
        profiles = registry['profiles']
        assigned = set(profiles['portable']['modules']) | set(profiles['framework']['modules']) | set(profiles['query']['modules'])
        if assigned != test_files:
            errors.append('Top-level test profile assignment is incomplete or contains unknown modules.')
        core = set(profiles['core']['modules'])
        if not core <= set(profiles['portable']['modules']):
            errors.append('Core profile is not a subset of the portable profile.')

        # The executable profile constants and the machine-readable registry are
        # both public interfaces.  Reject drift instead of letting CI, docs and
        # reviewer commands silently run different test sets.
        spec = importlib.util.spec_from_file_location(
            'authrefine_test_profiles', root / 'test_profiles.py'
        )
        if spec is None or spec.loader is None:
            errors.append('Could not load executable test profile definitions.')
        else:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            executable = {
                'core': list(module.CORE_TEST_MODULES),
                'portable': list(module.PORTABLE_TEST_MODULES),
                'framework': list(module.FRAMEWORK_TEST_MODULES),
                'query': list(module.QUERY_TEST_MODULES),
            }
            for name, modules in executable.items():
                if modules != profiles[name]['modules']:
                    errors.append(
                        f'Executable and registry definitions differ for the {name} profile.'
                    )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append('Invalid test profile registry: ' + str(exc))

    workflow_count = len(list((root/'.github/workflows').glob('*.yml')))
    if workflow_count < 3:
        errors.append('Repository does not contain the expected CI workflows.')

    result = {
        'check': 'repository-material-integrity',
        'python_sources_parsed': source_count,
        'top_level_test_files': len(list((root/'tests').glob('test_*.py'))),
        'workflow_files': workflow_count,
        'usage_document_present': readme.is_file(),
        'warnings': warnings,
        'errors': errors,
        'scope': 'Repository layout, source syntax, profile coverage, path/secret hygiene, and required files; research experiments are checked separately.',
    }
    print(json.dumps(result, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
