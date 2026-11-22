"""Run Blender integration suites in disposable, project-local user profiles."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
SUITES = {
    'core': ('tests_blender.py', 'TEST_SUMMARY'),
    'selection': ('tests_selection.py', 'SELECTION_TEST_SUMMARY'),
    'simplify': ('tests_simplify.py', 'SIMPLIFY_TEST_SUMMARY'),
    'fitting': ('tests_fitting.py', 'FITTING_TEST_SUMMARY'),
    'preview': ('tests_preview.py', 'PREVIEW_TEST_SUMMARY'),
    'upgrade': ('tests_upgrade.py', 'UPGRADE_TEST_SUMMARY'),
    'upgrade_current': ('tests_upgrade_current.py', 'CURRENT_UPGRADE_TEST_SUMMARY'),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blender', default=os.environ.get('BLENDER_BIN', 'blender'))
    parser.add_argument('--suite', choices=['all', *SUITES], default='all')
    parser.add_argument('--timeout', type=float, default=300, help='Seconds per suite')
    args = parser.parse_args()
    executable = shutil.which(args.blender)
    if not executable:
        parser.error('Blender not found. Pass --blender or set BLENDER_BIN.')
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    run_dir = ROOT / 'build/test-runs' / run_id
    run_dir.mkdir(parents=True)
    results = []
    suites = SUITES if args.suite == 'all' else {args.suite: SUITES[args.suite]}
    for name, (script, marker) in suites.items():
        suite_dir = run_dir / name
        profile = suite_dir / 'profile'
        output = suite_dir / 'output'
        output.mkdir(parents=True)
        profile.mkdir()
        env = os.environ.copy()
        env['BLENDER_USER_RESOURCES'] = str(profile)
        for suffix, directory in [('CONFIG', 'config'), ('SCRIPTS', 'scripts'),
                                  ('EXTENSIONS', 'extensions'), ('DATAFILES', 'datafiles')]:
            path = profile / directory
            path.mkdir()
            env['BLENDER_USER_' + suffix] = str(path)
        env['KR_TEST_PROFILE'] = str(profile)
        env['KR_TEST_OUTPUT'] = str(output)
        command = [executable, '--background', '--factory-startup', '--offline-mode',
                   '--python-exit-code', '1', '--python', str(ROOT / 'tests' / script)]
        print(f'Running {name}...', flush=True)
        start = time.monotonic()
        try:
            completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                       text=True, encoding='utf-8', errors='replace', timeout=args.timeout,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            log = completed.stdout + '\n' + completed.stderr
            record = {'suite': name, 'exit_code': completed.returncode, 'passed': False}
            for line in completed.stdout.splitlines():
                if line.startswith(marker + ' '):
                    record['summary'] = json.loads(line[len(marker) + 1:])
            record['passed'] = completed.returncode == 0 and record.get('summary', {}).get('passed') is True
        except subprocess.TimeoutExpired as exc:
            log = f'Suite exceeded {args.timeout} seconds.\n{exc}'
            record = {'suite': name, 'passed': False, 'timeout_seconds': args.timeout}
        record['seconds'] = round(time.monotonic() - start, 3)
        record['log'] = str((suite_dir / 'blender.log').relative_to(ROOT))
        (suite_dir / 'blender.log').write_text(log, encoding='utf-8')
        results.append(record)
        print(f"{name}: {'PASS' if record['passed'] else 'FAIL'} ({record['seconds']}s)", flush=True)
        if not record['passed']:
            print(log[-12000:], flush=True)
    report = {'passed': all(r['passed'] for r in results), 'blender': executable,
              'checks': sum(r.get('summary', {}).get('checks', 0) for r in results), 'suites': results}
    (run_dir / 'summary.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'checks': report['checks'],
                      'report': str(run_dir / 'summary.json')}, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
