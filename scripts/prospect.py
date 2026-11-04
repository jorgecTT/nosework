"""Runs the whole pipeline for one campaign, step by step. Safe to stop and run again: every step
picks up where it stopped and never repeats a site already read.

  1 discover   2 scan   3 registry (optional, off)   4 score   5 draft   6 verify   7 export

Usage:
  python3 prospect.py --campaign fl-miami --state FL --counties "Miami-Dade County" --max 300
  python3 prospect.py --campaign fl-miami --from score        # redo only from step 4 on
  python3 prospect.py --profile profiles/my-company --campaign ...   # any script accepts --profile
Options --sectors and --source are passed to discover. When draft stops (exit 2), the agent writes the
missing first lines in manual_lines.jsonl and runs again with --from draft.
"""
import argparse
import subprocess
import sys
from pathlib import Path

from common import PROFILE_DIR, add_profile_arg

HERE = Path(__file__).resolve().parent
STEPS = ['discover', 'scan', 'registry', 'score', 'draft', 'verify', 'export']


def main() -> None:
    ap = argparse.ArgumentParser(description='Run the 7-step prospecting pipeline for one campaign.')
    add_profile_arg(ap)
    ap.add_argument('--campaign', required=True)
    ap.add_argument('--state', help='a key of references/regions.json (for example FL)')
    ap.add_argument('--counties')
    ap.add_argument('--sectors')
    ap.add_argument('--source', default='both', choices=['osm', 'brave', 'both'])
    ap.add_argument('--max', type=int, default=0, help='new sites to read in this run')
    ap.add_argument('--from', dest='start', default='discover', choices=STEPS)
    ap.add_argument('--to', default='export', choices=STEPS)
    ap.add_argument('--registry', action='store_true', help='also run the optional state-registry step (off by default)')
    ap.add_argument('--offline', action='store_true', help='tests only: verify does not download the pages again')
    a = ap.parse_args()
    for step in STEPS[STEPS.index(a.start):STEPS.index(a.to) + 1]:
        if step == 'registry' and not (a.registry or a.start == 'registry'):
            continue
        cmd = [sys.executable, str(HERE / f'{step}.py'), '--campaign', a.campaign, '--profile', str(PROFILE_DIR)]
        if step == 'discover':
            if not a.state:
                sys.exit('discover needs --state (a key of references/regions.json, for example FL)')
            cmd += ['--state', a.state, '--source', a.source]
            cmd += ['--counties', a.counties] if a.counties else []
            cmd += ['--sectors', a.sectors] if a.sectors else []
        if step == 'scan' and a.max:
            cmd += ['--max', str(a.max)]
        if step == 'verify' and a.offline:
            cmd += ['--offline']
        print(f'\n=== {step} ===', flush=True)
        r = subprocess.run(cmd)
        if step == 'draft' and r.returncode == 2:
            sys.exit(f'\nPaused: first lines are missing. Write them (data/{a.campaign}/FOR_DRAFTING.md) and run again with '
                     f'--campaign {a.campaign} --from draft')
        if r.returncode != 0 and step != 'verify':
            sys.exit(f'Step {step} failed (code {r.returncode}). Read the error above and run.log; fix it and run again with '
                     f'--from {step}.')
    subprocess.run([sys.executable, str(HERE / 'report.py'), '--campaign', a.campaign, '--profile', str(PROFILE_DIR)])
    subprocess.run([sys.executable, str(HERE / 'coverage.py'), '--profile', str(PROFILE_DIR)])
    print(f'\nDone. Read data/{a.campaign}/SUMMARY.md and, for the next run, data/READ_FIRST.md')


if __name__ == '__main__':
    main()
