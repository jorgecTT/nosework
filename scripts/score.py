"""Step 4 - decides, for every company read, whom to write to, through which channel and how good a lead it is.

From scan.jsonl (+ registry.jsonl when it exists) it writes leads.jsonl, one line per company:
  channel   email       a published email that is not a jobs/privacy/noreply inbox
            form        no usable email but a contact form (goes to the forms list; nosework never sends it)
            no_contact  neither: kept in the leads file, never contacted
  contact   the person whose name is in the chosen email (owner, manager...) or the general inbox
  points    signals + sector priority + size + age + named contact; see references/RULES.md, "Points"
  status    to_draft, form, queued, discarded (with the reason)
Companies already contacted (comun.already_contacted: contacts.csv, suppress.txt, data/imports/) are dropped here.
New ids (prefix and base from the settings) are given here, once, and kept in ids.json.

Usage: python3 score.py --campaign fl-miami
"""
import argparse
import datetime as dt
import json

from common import (CONFIG, FREE_MAIL, PROFILE, add_profile_arg, already_contacted, campaign_dir, load_sectors, log, next_ids,
                    read_jsonl, write_jsonl)
from mail import is_disposable, is_role, mail_domain

YEAR = dt.date.today().year
SCORING = PROFILE.get('scoring', {})
PRIORITY_POINTS = {int(k): v for k, v in {'1': 2, '2': 1, '3': 0, **SCORING.get('priority_points', {})}.items()}
SIZE_POINTS = {'small': 2, 'medium': 2, 'multi_site': 2, 'large': 1, **SCORING.get('size_points', {})}
LADDER = PROFILE.get('offer_ladder', {})
# Role names that mean "the company's front desk". English first; a few Spanish ones for sites in Spanish.
GENERAL_INBOX = ['info', 'contact', 'contacto', 'office', 'hello', 'hola', 'admin', 'sales', 'ventas', 'inquiries',
                 'customerservice', 'service', 'team', 'mail', 'general']


def choose_contact(row: dict) -> tuple[dict | None, dict | None]:
    """(email entry, person): a decision maker whose own address is published beats the general inbox,
    which beats anyone else. Jobs, privacy and noreply inboxes never count."""
    good = [c for c in row.get('emails', []) if not c['wrong_inbox'] and not is_disposable(c['email'])
            and mail_domain(c['email'].split('@')[1])[0] is not False]
    if not good:
        return None, None
    people = {p['email']: p for p in row.get('people', []) if p.get('email')}
    for c in good:
        p = people.get(c['email'])
        if p and p.get('decides'):
            return c, p
    for c in good:  # a personal address (not a role inbox, Reacher's list) of someone not on the team page
        if not is_role(c['email']) and c['email'].split('@')[1] not in FREE_MAIL:
            return c, people.get(c['email'])
    for c in good:
        if c['email'].split('@')[0] in GENERAL_INBOX:
            return c, None
    for c in good:
        if c['email'] in people:
            return c, people[c['email']]
    return good[0], None


def age_of(row: dict, reg: dict) -> dict:
    if reg.get('registry_date'):
        y = int(reg['registry_date'][:4])
        return {'since': y, 'source': reg['registry'], 'detail': f"registered on {reg['registry_date']}"}
    a = row.get('age', {})
    if a.get('founded'):
        return {'since': a['founded'], 'source': 'its site', 'detail': a.get('how', '')}
    if a.get('oldest_copyright'):
        return {'since': a['oldest_copyright'], 'source': 'its site (copyright)', 'detail': 'at least since that year'}
    return {'since': None, 'source': '', 'detail': 'unknown'}


def _rule_matches(when: dict, ctx: dict) -> bool:
    kinds = ctx['signals']
    checks = [
        ('sectors' not in when) or ctx['sector'] in when['sectors'],
        ('signals_any' not in when) or bool(kinds & set(when['signals_any'])),
        ('signals_all' not in when) or set(when['signals_all']) <= kinds,
        ('signals_none' not in when) or not (kinds & set(when['signals_none'])),
        (not when.get('missing_alt_version')) or not ctx['has_alt'],
        (not when.get('site_dated')) or ctx['dated'],
    ]
    return all(checks)


def choose_offer(row: dict, sector: dict, ladder: dict | None = None) -> tuple[str, str]:
    """The offer ladder from the profile (profile.json -> offer_ladder), one offer per email.
    Partner sectors always get their own offer. Otherwise the rules are tried top to bottom and the first one
    that matches wins; 'sector' means the offer of the company's own sector, which is also the fallback.
    An alternate offer that is switched off ("active": false) is skipped."""
    ladder = LADDER if ladder is None else ladder
    own = sector.get('offer', 'default')
    if own in ladder.get('partner_offers', []):
        return own, 'partner: the offer of its sector'
    ctx = {'signals': {s['id'] for s in row.get('signals', [])}, 'sector': sector.get('id'),
           'has_alt': bool(row.get('has_alt_version')), 'dated': bool(row.get('site_health', {}).get('dated'))}
    alternates = ladder.get('alternates', {})
    for rule in ladder.get('rules', []):
        offer = own if rule['offer'] == 'sector' else rule['offer']
        if offer in alternates and not alternates[offer].get('active', True):
            continue
        if _rule_matches(rule.get('when', {}), ctx):
            why = rule.get('reason', 'rule matched')
            if rule.get('when', {}).get('signals_any'):
                why += ' (' + ' '.join(sorted(ctx['signals'] & set(rule['when']['signals_any']))) + ')'
            return offer, why
    return own, "the offer of its sector"


def points_for(row: dict, sector: dict, size: dict, age: dict, person) -> int:
    pts = sum(s['points'] for s in row.get('signals', [])) + PRIORITY_POINTS.get(sector.get('priority', 3), 0)
    pts += SIZE_POINTS.get(size.get('band'), 0)
    if age['since'] and YEAR - age['since'] <= SCORING.get('new_company_years', 2):
        pts += SCORING.get('new_company_bonus', 1)  # a new company is still writing its documents
    if person:
        pts += SCORING.get('named_contact_bonus', 1)
    return pts


def main() -> None:
    ap = argparse.ArgumentParser(description='Step 4: choose whom to write to, through which channel, and score the lead.')
    add_profile_arg(ap)
    ap.add_argument('--campaign', required=True)
    a = ap.parse_args()
    camp = campaign_dir(a.campaign)
    sectors = {s['id']: s for s in load_sectors()}
    regs = {r['domain']: r for r in read_jsonl(camp / 'registry.jsonl')}
    domains, emails = already_contacted()
    own_queue = {r['domain'] for r in read_jsonl(camp / 'exported.jsonl')}
    resector_file = camp / 'change_sector.txt'  # "domain sector" per line: the agent fixes a wrong sector
    resector = dict(l.split()[:2] for l in resector_file.read_text(encoding='utf-8').splitlines() if len(l.split()) >= 2) if resector_file.exists() else {}
    removed_file = camp / 'remove.txt'  # domains taken out by hand after reading the email
    removed = {l.strip().lower() for l in removed_file.read_text(encoding='utf-8').splitlines() if l.strip()} if removed_file.exists() else set()
    ids_file = camp / 'ids.json'
    ids = json.loads(ids_file.read_text(encoding='utf-8')) if ids_file.exists() else {}
    min_points = CONFIG['min_points_for_email']
    leads, seen = [], set()
    for row in read_jsonl(camp / 'scan.jsonl'):
        if row.get('read_status') != 'ok' or row['domain'] in seen:
            continue
        seen.add(row['domain'])
        if resector.get(row['domain']) in sectors:
            row = {**row, 'sector': resector[row['domain']]}
        sector = sectors.get(row['sector'], {'id': row['sector'], 'priority': 3, 'name': row['sector']})
        email, person = choose_contact(row)
        age = age_of(row, regs.get(row['domain'], {}))
        size = row.get('size', {})
        points = points_for(row, sector, size, age, person)
        offer, why_offer = choose_offer(row, sector)
        lead = {'domain': row['domain'], 'name': row['name'], 'name_reliable': row.get('name_reliable', True),
                'offer': offer, 'offer_reason': why_offer, 'site_health': row.get('site_health', {}), 'sector': row['sector'],
                'sector_name': sector.get('name', row['sector']), 'city': row.get('city') or '', 'county': row['county'],
                'state': row['state'], 'site': row['site'], 'phones': row.get('phones', []),
                'site_locale': row.get('site_locale', 'en'), 'has_alt_version': row.get('has_alt_version'),
                'signals': row.get('signals', []), 'size': size, 'age': age, 'people': row.get('people', []),
                'forms': row.get('forms', []), 'summary': row.get('summary', {}), 'points': points}
        e_dom = email['email'].split('@')[1] if email else ''
        if not row.get('in_region', True):
            lead.update(channel='outside', status='discarded', reason='its site does not say it is in that state or city')
        elif (size.get('locations') or 0) >= CONFIG['max_locations'] or (size.get('employees') or 0) >= CONFIG['max_employees']:
            lead.update(channel='chain', status='discarded', reason='chain or large company (decisions are made elsewhere)')
        elif not row.get('name_on_site', True):
            lead.update(channel='doubtful', status='discarded', reason="the company's name does not appear on that site")
        elif row['domain'] in removed:
            lead.update(channel='removed', status='discarded', reason='removed by hand (remove.txt)')
        elif row['domain'] in own_queue:
            lead.update(channel='email', email=email['email'] if email else '', contact=person or {}, status='queued',
                        reason='already in the queue of this campaign')
        elif row['domain'] in domains or (e_dom and e_dom not in FREE_MAIL and e_dom in domains) or (email and email['email'] in emails):
            lead.update(channel='already_contacted', status='discarded',
                        reason='already contacted, queued, suppressed or imported (contacts.csv, suppress.txt, data/imports)')
        elif email:
            lead.update(channel='email', email=email['email'], email_page=email['page'],
                        contact=person or {}, status='to_draft' if points >= min_points else 'discarded',
                        reason='' if points >= min_points else f'too few points ({points})')
        elif row.get('forms'):
            lead.update(channel='form', status='form', reason='no published email, has a contact form')
        else:
            lead.update(channel='no_contact', status='discarded', reason='no email or form on its site')
        leads.append(lead)
    need = [l for l in leads if l['status'] in ('to_draft', 'form') and l['domain'] not in ids]
    for l, new in zip(need, next_ids(len(need)) if need else []):
        ids[l['domain']] = new
    ids_file.write_text(json.dumps(ids, indent=0), encoding='utf-8')
    for l in leads:
        l['id'] = ids.get(l['domain'], '')
    leads.sort(key=lambda l: -l['points'])
    write_jsonl(camp / 'leads.jsonl', leads)
    by = {}
    for l in leads:
        by[l['status']] = by.get(l['status'], 0) + 1
    log(camp, f'score: {len(leads)} companies -> {by}')


if __name__ == '__main__':
    main()
