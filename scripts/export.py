"""Step 7 - turns the verified drafts into the files people and your sending tool use. Sends nothing.

Writes in the campaign folder:
  queue-<campaign>.json   the queue for whatever sends your email (mail merge, CRM, a script of your own):
                          id, name, city, to, subject, body, fit, kind, offer, variant, batch; email leads only
  BATCHES_<campaign>.md   every email in full, in batches, for you to read before anything goes out
  FORMS_<campaign>.csv    the companies to contact through their website form, with the form's page,
                          action, fields, captcha and the message ready (nosework never submits a form)
  LEADS_<campaign>.csv    every company read, contacted or not: people, size, age, channel, points, reason
  SUMMARY.md              the numbers of the whole run, the first thing to read
Exported ids go to exported.jsonl, so the next run only adds new ones. The contacts register
(data/contacts.csv) is refreshed so the queued companies are never prospected again.

Usage: python3 export.py --campaign fl-miami
"""
import argparse
import csv
import json
import time

from common import CONFIG, DATA, SENDER, add_profile_arg, append_jsonl, campaign_dir, campaigns, log, read_jsonl

SIZE_LABELS = {'unknown': 'unknown', 'micro': 'micro (under 10)', 'small': 'small (10 to 49)', 'medium': 'medium (50 to 249)',
               'large': 'large (250 or more)', 'multi_site': 'small or more (several locations)'}
LEAD_COLUMNS = ['id', 'company', 'sector', 'city', 'county', 'state', 'site', 'channel', 'offer', 'email', 'contact', 'role',
                'people_on_site', 'size_band', 'employees_per_site', 'since', 'age_source', 'has_alt_version', 'signals',
                'points', 'lead_status', 'reason', 'phone']
FORM_COLUMNS = ['id', 'company', 'sector', 'city', 'state', 'form_page', 'action', 'method', 'fields', 'captcha', 'provider', 'message']


def fit_of(points: int) -> int:
    return 3 if points >= 8 else 2 if points >= 6 else 1


def interleave(emails: list[dict]) -> list[dict]:
    """Best first, and sectors mixed so one bad day doesn't hit a single kind of business."""
    emails = sorted(emails, key=lambda d: -d['points'])
    by_sector, ordered = {}, []
    for d in emails:
        by_sector.setdefault(d['sector'], []).append(d)
    while any(by_sector.values()):
        for s in list(by_sector):
            if by_sector[s]:
                ordered.append(by_sector[s].pop(0))
    return ordered


def lead_row(l: dict) -> list:
    c = l.get('contact') or {}
    return [l.get('id', ''), l['name'], l['sector'], l['city'], l['county'], l.get('state', ''), l['site'], l['channel'],
            l.get('offer', ''), l.get('email', ''), c.get('name', ''), c.get('role', ''),
            '; '.join(f"{p['name']} ({p['role']})" for p in l.get('people', [])[:5]),
            SIZE_LABELS.get(l['size'].get('band', 'unknown'), ''), l['size'].get('employees') or '',
            l['age'].get('since') or '', l['age'].get('source', ''), 'yes' if l.get('has_alt_version') else 'no',
            ' '.join(s['id'] for s in l['signals']), l['points'], l['status'], l.get('reason', ''),
            ' '.join(l.get('phones', [])[:1])]


def main() -> None:
    ap = argparse.ArgumentParser(description='Step 7: write the queue, the batches to read, the forms list and the leads table.')
    add_profile_arg(ap)
    ap.add_argument('--campaign', required=True)
    a = ap.parse_args()
    camp = campaign_dir(a.campaign)
    leads = read_jsonl(camp / 'leads.jsonl')
    ok = read_jsonl(camp / 'verified.jsonl')
    exported = {r['id'] for r in read_jsonl(camp / 'exported.jsonl')}
    emails = [d for d in ok if d['channel'] == 'email' and d['id'] not in exported]
    forms = [d for d in ok if d['channel'] == 'form']
    ordered = interleave(emails)
    queue_path = camp / f'queue-{a.campaign}.json'
    old = json.loads(queue_path.read_text(encoding='utf-8')) if queue_path.exists() else []
    start_batch = max([i['batch'] for i in old], default=0)
    items = [{'id': d['id'], 'name': d['name'], 'city': f"{d['city']}, {d['state']}", 'to': d['to'],
              'subject': d['subject'], 'body': d['body'], 'fit': fit_of(d['points']), 'kind': d['sector'],
              'offer': d.get('offer_kind') or d.get('offer', ''), 'variant': d.get('variant', ''),
              'batch': start_batch + n // CONFIG['batch_size'] + 1} for n, d in enumerate(ordered)]
    queue_path.write_text(json.dumps(old + items, ensure_ascii=False, indent=1), encoding='utf-8')
    for d in ordered:
        append_jsonl(camp / 'exported.jsonl', {'id': d['id'], 'domain': d['domain'], 'to': d['to'], 'date': time.strftime('%Y-%m-%d')})
    all_items = old + items
    md = [f'# Emails of campaign {a.campaign}: {len(all_items)} in total, in batches of {CONFIG["batch_size"]}', '',
          f"They go out from **{SENDER.get('from_mailbox', '')}**. Nothing goes out until you approve it.", '']
    when = {r['id']: r.get('date', '') for r in read_jsonl(camp / 'exported.jsonl')}
    new_ids = {i['id'] for i in items}
    md += [f'**New in this run: {len(new_ids)}.** The others were exported earlier (and may already be loaded and approved): '
           'each one says when. Only the new ones wait for review.', '']
    for i in all_items:
        tag = 'NEW' if i['id'] in new_ids else f"exported on {when.get(i['id'], '?')}"
        md += ['---', '', f'## Batch {i["batch"]} | {i["id"]} | {i["name"]} ({i["city"]}) | {i["kind"]} | {tag}',
               f'**To:** {i["to"]}  ', f'**Subject:** {i["subject"]}', '', '```', i['body'], '```', '']
    (camp / f'BATCHES_{a.campaign}.md').write_text('\n'.join(md), encoding='utf-8')
    with (camp / f'FORMS_{a.campaign}.csv').open('w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(FORM_COLUMNS)
        for d in forms:
            for f in d.get('forms', [])[:1]:
                w.writerow([d['id'], d['name'], d['sector'], d['city'], d['state'], f['page'], f['action'], f['method'],
                            ' '.join(f['fields']), f['captcha'], f['provider'], d['form_message']])
    with (camp / f'LEADS_{a.campaign}.csv').open('w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(LEAD_COLUMNS)
        for l in leads:
            w.writerow(lead_row(l))
    write_summary(camp, a.campaign, leads, ok, all_items, forms)
    merge_all()
    refresh_contacts()
    log(camp, f'export: {len(items)} new emails in the queue ({len(all_items)} in total), {len(forms)} forms -> SUMMARY.md')


def refresh_contacts() -> None:
    """Queued companies go into data/contacts.csv so no later campaign prospects them again."""
    try:
        import contacts
        contacts.rebuild()
    except Exception as e:  # the register is a safety net; a failure here must not lose the export
        print(f'warning: could not refresh data/contacts.csv ({type(e).__name__}: {e})')


def merge_all() -> None:
    """data/LEADS_ALL.csv and FORMS_ALL.csv: every campaign in one file each, with a 'campaign' column."""
    for kind in ('LEADS', 'FORMS'):
        rows, header = [], None
        for camp in campaigns():
            for f in sorted(camp.glob(f'{kind}_*.csv')):
                with f.open(newline='', encoding='utf-8') as fh:
                    r = csv.reader(fh)
                    h = next(r, None)
                    if not h:
                        continue
                    header = header or ['campaign'] + h
                    rows += [[camp.name] + row for row in r]
        if header:
            with (DATA / f'{kind}_ALL.csv').open('w', newline='', encoding='utf-8') as fh:
                w = csv.writer(fh)
                w.writerow(header)
                w.writerows(rows)


def write_summary(camp, name, leads, ok, queue, forms) -> None:
    def lines(path):
        return sum(1 for _ in path.open(encoding='utf-8')) if path.exists() else 0
    cands, scanned = lines(camp / 'candidates.jsonl'), lines(camp / 'scan.jsonl')
    rejected = len(read_jsonl(camp / 'rejected.jsonl'))
    active = {l.get('id') for l in leads if l['status'] in ('to_draft', 'form')}
    pending = sum(1 for d in read_jsonl(camp / 'drafts.jsonl') if d.get('pending') and d['id'] in active)

    def count(key):
        out = {}
        for l in leads:
            k = key(l)
            out[k] = out.get(k, 0) + 1
        return sorted(out.items(), key=lambda x: -x[1])

    md = [f'# Summary of campaign {name}', '', f'Updated: {time.strftime("%Y-%m-%d %H:%M")}', '',
          '| Step | How many |', '|---|---|', f'| Companies found with a website | {cands} |', f'| Sites read | {scanned} |',
          f'| Companies evaluated | {len(leads)} |', f'| Emails that passed the filter | {sum(1 for d in ok if d["channel"] == "email")} |',
          f'| In the queue to send | {len(queue)} |', f'| To contact through a form | {len(forms)} |',
          f'| Waiting for their first line (FOR_DRAFTING.md) | {pending} |', f'| Did not pass the filter (VERIFICATION.md) | {rejected} |', '',
          '## Why they were discarded', ''] + [f'- {n} x {k}' for k, n in count(lambda l: l.get('reason') or l['status']) if k != 'to_draft']
    md += ['', '## By sector (everything evaluated)', ''] + [f'- {k}: {n}' for k, n in count(lambda l: l['sector'])]
    md += ['', '## By size', ''] + [f'- {SIZE_LABELS.get(k, k)}: {n}' for k, n in count(lambda l: l['size'].get('band', 'unknown'))]
    md += ['', '## With a named person as contact', '',
           f"- {sum(1 for l in leads if (l.get('contact') or {}).get('name'))} of {sum(1 for l in leads if l['channel'] == 'email')} with an email"]
    (camp / 'SUMMARY.md').write_text('\n'.join(md) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
