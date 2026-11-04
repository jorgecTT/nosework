"""How far each campaign has got, in a few lines (cheap to read: no need to open the big files).

Usage: python3 status.py [--campaign fl-miami]
"""
import argparse
import json

from common import DATA, add_profile_arg, campaigns, read_jsonl

FILES = [('candidates.jsonl', 'found'), ('scan.jsonl', 'sites read'), ('leads.jsonl', 'evaluated'),
         ('drafts.jsonl', 'drafts'), ('verified.jsonl', 'pass the filter'), ('rejected.jsonl', 'do not pass'),
         ('exported.jsonl', 'already in the queue')]


def main() -> None:
    ap = argparse.ArgumentParser(description='One-line progress of each campaign.')
    add_profile_arg(ap)
    ap.add_argument('--campaign')
    a = ap.parse_args()
    camps = [DATA / a.campaign] if a.campaign else campaigns()
    if not camps:
        print('No campaigns yet.')
    for c in camps:
        parts = []
        for f, label in FILES:
            rows = read_jsonl(c / f)
            if f == 'drafts.jsonl':
                pend = sum(1 for r in rows if r.get('pending'))
                parts.append(f'{len(rows) - pend} {label} (+{pend} without a first line)')
            elif rows or f == 'candidates.jsonl':
                parts.append(f'{len(rows)} {label}')
        leads = read_jsonl(c / 'leads.jsonl')
        forms = sum(1 for l in leads if l['channel'] == 'form')
        print(f'{c.name}: ' + ' | '.join(parts) + (f' | {forms} with a form only' if leads else ''))
        done = c / 'sources_done.json'
        if done.exists():
            print(f'   searches done: {len(json.loads(done.read_text(encoding="utf-8")))}')


if __name__ == '__main__':
    main()
