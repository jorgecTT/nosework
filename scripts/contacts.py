"""The local contact register: who was queued, who you actually wrote to, and what happened. Nothing is
contacted twice because of it. nosework sends nothing, so YOU tell it what you sent.

  data/contacts.csv      the register (this script builds it from your campaigns and keeps your edits)
  data/suppress.txt      optional, yours: do-not-contact list, one email or domain per line (# comments)
  data/imports/*.csv     optional, yours: any CSV with an email and/or domain/website column (a CRM export,
                         your newsletter list, a bounce list). Every address in there counts as contacted.

Statuses, most decisive first: bounced, replied, auto_reply, blocked, sent, queued, form, found.
These block a new first email: queued, sent, replied, auto_reply, bounced, blocked.

Usage:
  python3 contacts.py                       rebuild the register from every campaign (keeps statuses you set)
  python3 contacts.py mark bob@example.org sent --note "first email, batch 3"
  python3 contacts.py mark example.org blocked        (a domain: everyone there is blocked)
  python3 contacts.py summary
Rows are never deleted, and a status you set is never replaced by a less decisive one.
"""
import argparse
import csv
import datetime as dt
import sys
from pathlib import Path

from common import BLOCKING_STATUSES, DATA, FREE_MAIL, add_profile_arg, campaigns, read_jsonl

COLUMNS = ['id', 'company', 'sector', 'city', 'state', 'email', 'domain', 'contact', 'offer', 'variant', 'status',
           'sent_date', 'notes', 'campaign']
RANK = ['bounced', 'replied', 'auto_reply', 'blocked', 'sent', 'queued', 'form', 'found']
CONTACTS = DATA / 'contacts.csv'


def key_of(row: dict) -> str:
    return (row.get('email') or '').lower() or (row.get('domain') or '').lower()


def read_register(path: Path = CONTACTS) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline='', encoding='utf-8') as fh:
        return [{c: r.get(c, '') or '' for c in COLUMNS} for r in csv.DictReader(fh)]


def write_register(rows: list[dict], path: Path = CONTACTS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    with tmp.open('w', newline='', encoding='utf-8') as fh:  # written aside and swapped in whole
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction='ignore')
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (RANK.index(r['status']) if r['status'] in RANK else 99, r['sent_date'], r['id'])))
    tmp.replace(path)


def merge(rows: list[dict], new: dict) -> None:
    """Adds `new` to `rows` in place. An existing row keeps its more decisive status and its non-empty fields."""
    key = key_of(new)
    old = next((r for r in rows if key and key_of(r) == key), None)
    if old is None:
        rows.append({c: new.get(c, '') or '' for c in COLUMNS})
        return
    if new['status'] in RANK and (old['status'] not in RANK or RANK.index(new['status']) < RANK.index(old['status'])):
        old['status'] = new['status']
    for c in COLUMNS:
        if not old.get(c) and new.get(c):
            old[c] = new[c]


def from_campaigns() -> list[dict]:
    """Register rows for every company the campaigns found, queued or exported."""
    out = []
    for camp in campaigns():
        leads = {l.get('id'): l for l in read_jsonl(camp / 'leads.jsonl') if l.get('id')}
        drafts = {d['id']: d for d in read_jsonl(camp / 'drafts.jsonl') if not d.get('pending')}
        for e in read_jsonl(camp / 'exported.jsonl'):
            l, d = leads.get(e['id'], {}), drafts.get(e['id'], {})
            out.append({'id': e['id'], 'company': l.get('name', ''), 'sector': l.get('sector', ''), 'city': l.get('city', ''),
                        'state': l.get('state', ''), 'email': e.get('to', ''), 'domain': '' if e.get('to', '').split('@')[-1] in FREE_MAIL else e.get('domain', ''),
                        'contact': (l.get('contact') or {}).get('name', ''), 'offer': d.get('offer_kind', ''),
                        'variant': d.get('variant', ''), 'status': 'queued', 'sent_date': '', 'notes': '', 'campaign': camp.name})
        queued = {e['id'] for e in read_jsonl(camp / 'exported.jsonl')}
        for l in leads.values():
            if l['id'] in queued or l.get('status') not in ('to_draft', 'form'):
                continue
            out.append({'id': l['id'], 'company': l['name'], 'sector': l['sector'], 'city': l['city'], 'state': l['state'],
                        'email': l.get('email', ''), 'domain': l['domain'], 'contact': (l.get('contact') or {}).get('name', ''),
                        'offer': l.get('offer', ''), 'variant': '', 'status': 'form' if l['status'] == 'form' else 'found',
                        'sent_date': '', 'notes': l.get('reason', ''), 'campaign': camp.name})
    return out


def rebuild(path: Path = CONTACTS) -> list[dict]:
    rows = read_register(path)
    for r in from_campaigns():
        merge(rows, r)
    write_register(rows, path)
    return rows


def mark(target: str, status: str, note: str = '', path: Path = CONTACTS) -> int:
    """Set the status of an email (one row) or a domain (every row of that domain). Returns rows changed."""
    if status not in RANK:
        raise ValueError(f'status must be one of {", ".join(RANK)}')
    rows = read_register(path)
    target = target.lower().strip()
    hit = [r for r in rows if target in (r['email'].lower(), r['domain'].lower())]
    if not hit:
        row = {c: '' for c in COLUMNS}
        row.update(email=target if '@' in target else '', domain='' if '@' in target else target, status=status)
        rows.append(row)
        hit = [row]
    for r in hit:
        r['status'] = status  # an explicit mark by the user always wins
        if status == 'sent' and not r['sent_date']:
            r['sent_date'] = dt.date.today().isoformat()
        if note:
            r['notes'] = (r['notes'] + ' | ' + note).strip(' |')
    write_register(rows, path)
    return len(hit)


def summary(rows: list[dict]) -> str:
    count = {}
    for r in rows:
        count[r['status']] = count.get(r['status'], 0) + 1
    lines = [f'{len(rows)} contacts in {CONTACTS}']
    lines += [f'  {s}: {count[s]}' + ('  (blocks a new first email)' if s in BLOCKING_STATUSES else '') for s in RANK if s in count]
    return '\n'.join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description='Local contact register (data/contacts.csv).')
    add_profile_arg(ap)
    sub = ap.add_subparsers(dest='cmd')
    m = sub.add_parser('mark', help='set the status of an email or a domain')
    m.add_argument('target')
    m.add_argument('status', choices=RANK)
    m.add_argument('--note', default='')
    sub.add_parser('summary', help='counts by status')
    sub.add_parser('rebuild', help='rebuild from the campaigns (default)')
    a = ap.parse_args()
    if a.cmd == 'mark':
        print(f'{mark(a.target, a.status, a.note)} row(s) set to {a.status}')
        return 0
    if a.cmd == 'summary':
        print(summary(read_register()))
        return 0
    print(summary(rebuild()))
    return 0


if __name__ == '__main__':
    sys.exit(main())
