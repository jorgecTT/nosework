"""Step 6 - the gate. Nothing reaches the queue or the forms list without passing here.

For every draft it checks, again and live where it matters:
  1. the email is still published on the page where it was found (the page is downloaded again now),
  2. the email belongs to the site's domain or is a free mailbox, and it is not a jobs/privacy/noreply inbox,
  3. nobody else in the batch has that domain, and it was never contacted (common.already_contacted),
  4. the first line passes the same rules as draft.py and its proof is in the saved pages,
  5. the whole email has no banned words and the right signature and opt-out line.
A draft that fails goes to rejected.jsonl with the reasons; the rest to verified.jsonl.
VERIFICATION.md ends with "RESULT: OK" when at least one passed and nothing systemic broke.

Usage: python3 verify.py --campaign fl-miami [--offline]   (--offline skips check 1, only for tests)
"""
import argparse
import concurrent.futures as cf
import sys
import time

from common import (FREE_MAIL, SENDER, WRONG_INBOX, add_profile_arg, already_contacted, campaign_dir, decode_cfemail, get,
                    locale_text, log, profile_placeholders, read_jsonl, write_jsonl)
from draft import BANNED, evidence_text, line_problems
from mail import is_disposable, mail_domain
from quality import Vocabulary, problems as quality_problems


def check(d: dict, camp, contacted: tuple, online: bool, vocab=None, before=()) -> list[str]:
    p = []
    domains, emails = contacted
    to = d.get('to', '')
    if d['channel'] == 'email':
        if not to or '@' not in to:
            return ['has no email']
        e_dom = to.split('@')[1]
        if WRONG_INBOX.match(to.split('@')[0]):
            p.append(f'{to} is an inbox that does not buy (jobs, privacy, noreply)')
        if e_dom not in FREE_MAIL and e_dom != d['domain'] and not e_dom.endswith('.' + d['domain']) and not d['domain'].endswith('.' + e_dom):
            p.append(f'the email is on another domain ({e_dom})')
        if to in emails or d['domain'] in domains or (e_dom not in FREE_MAIL and e_dom in domains):
            p.append('already contacted, queued, suppressed or imported')
        if is_disposable(to):
            p.append(f'{to} is a disposable address')
        ok_mx, why = mail_domain(e_dom)
        if ok_mx is False:
            p.append(f'{e_dom}: {why} (it would bounce)')
        if online:
            status, html, _ = get(d['email_page'])
            for wait in (5, 20):  # a dropped connection is retried: it is our network, not their site
                if isinstance(status, int):
                    break
                time.sleep(wait)
                status, html, _ = get(d['email_page'])
            if isinstance(status, str):
                p.append(f'could not be checked now ({status}); it will be tried again on the next run')
            elif status != 200:
                p.append(f'the email page no longer answers ({status})')
            elif to not in decode_cfemail(html).lower().replace('&#64;', '@'):
                p.append(f'{to} no longer appears on {d["email_page"]}')
    p += line_problems(d['first_line'], d['proof'], d['locale'], evidence_text(camp, d['domain']))
    p += quality_problems(d['first_line'], d['proof'], d['name'], before, vocab, d['domain'])
    body = d['body'].lower()
    rest = body.replace(d['first_line'].lower(), '')
    for b in BANNED:
        if b.isalpha() and len(b) > 3 and b in rest:
            p.append(f"the email uses '{b}'")
    if (locale_text(SENDER['signature'], d['locale']).split('\n')[0].lower() not in body
            or locale_text(SENDER['opt_out'], d['locale']).split('\n')[0].lower() not in body):
        p.append('the signature or the opt-out line is missing')
    return p


def main() -> None:
    ap = argparse.ArgumentParser(description='Step 6: re-check every draft (email still published, rules, banned words).')
    add_profile_arg(ap)
    ap.add_argument('--campaign', required=True)
    ap.add_argument('--offline', action='store_true', help='tests only: do not download the pages again')
    a = ap.parse_args()
    if profile_placeholders():
        sys.exit('The active profile still has REPLACE_ME values: finish the onboarding first.\nRESULT: FAIL')
    camp = campaign_dir(a.campaign)
    active = {l['id'] for l in read_jsonl(camp / 'leads.jsonl') if l['status'] in ('to_draft', 'form')}
    # A draft whose company was taken out later (remove.txt, already contacted...) never reaches the queue.
    drafts = [d for d in read_jsonl(camp / 'drafts.jsonl') if not d.get('pending') and d['id'] in active]
    if not drafts:
        print('There are no drafts. Run draft.py first.\nRESULT: FAIL')
        sys.exit(1)
    contacted = already_contacted()
    # Rows already exported in an earlier run are not re-checked against "already contacted" (they are in it).
    exported = {r['id'] for r in read_jsonl(camp / 'exported.jsonl')}
    drafts = [d for d in drafts if d['id'] not in exported]
    with cf.ThreadPoolExecutor(6) as ex:
        vocab = Vocabulary(camp)
        lines = {d['id']: d['first_line'] for d in drafts}
        results = list(ex.map(lambda d: (d, check(d, camp, contacted, not a.offline, vocab,
                                                   [l for k, l in lines.items() if k < d['id']])), drafts))
    ok, bad, seen_domains = [], [], set()
    for d, probs in results:
        e_dom = d['to'].split('@')[-1] if '@' in d.get('to', '') else ''
        key = e_dom if e_dom and e_dom not in FREE_MAIL else d.get('to') or d['domain']
        if key in seen_domains:
            probs = probs + ['another company in the batch has the same domain']
        seen_domains.add(key)
        (bad if probs else ok).append({**d, 'problems': probs})
    write_jsonl(camp / 'verified.jsonl', ok)
    write_jsonl(camp / 'rejected.jsonl', bad)
    by_reason = {}
    for b in bad:
        for pr in b['problems']:
            k = pr.split('(')[0].split("'")[0].strip()[:70]
            by_reason[k] = by_reason.get(k, 0) + 1
    md = [f'# Verification of {a.campaign}', '', f'- Checked: {len(results)}', f'- Pass: {len(ok)}', f'- Do not pass: {len(bad)}',
          f'- Live check of the email: {"no (--offline)" if a.offline else "yes"}', '', '## Why they do not pass', '']
    md += [f'- {n} x {k}' for k, n in sorted(by_reason.items(), key=lambda x: -x[1])] or ['- (none)']
    md += ['', '## Detail of the ones that do not pass', ''] + [f"- {b['id']} {b['name']}: {'; '.join(b['problems'])}" for b in bad]
    result = 'OK' if ok and not a.offline else 'FAIL'
    md += ['', f'RESULT: {result}' + ('' if ok else ' (none passed)') + (' (the live check is missing)' if a.offline else '')]
    (camp / 'VERIFICATION.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    log(camp, f'verify: {len(ok)} pass, {len(bad)} do not pass -> VERIFICATION.md - RESULT: {result}')
    sys.exit(0 if result == 'OK' else 1)


if __name__ == '__main__':
    main()
