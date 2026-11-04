"""Step 5 - writes the email for every lead, from what its website says.

The email is a fixed structure (see references/TEMPLATES.md) with one personal piece: the first line, a sentence
about something concrete on that company's site. **The agent running the skill writes it** (Claude, Codex,
Gemini...), the same model, no outside API: this step writes FOR_DRAFTING.md with the few facts of each company,
the agent answers in manual_lines.jsonl, and this step runs again. Code accepts a line only if its "proof"
(4 to 15 words copied from the site) appears letter by letter in the saved pages and the line passes
line_problems() and quality.problems(). Nothing is invented, nothing is sent anywhere.
Writes <campaign>/drafts.jsonl (saved after every company). Exits with code 2 while lines are missing.

Usage: python3 draft.py --campaign fl-miami
"""
import argparse
import datetime as dt
import re
import sys

from common import (DEFAULT_LOCALE, PROFILE, SENDER, TEMPLATES, VARIANTS, add_profile_arg, append_jsonl, assign_variant,
                    campaign_dir, load_sectors, locale_text, log, norm, page_text, profile_placeholders, read_jsonl, write_jsonl)
from quality import Vocabulary, problems as quality_problems

# Universal bans: style, flattery, cliche openers, accusations and criticism of their website. Company-specific
# bans (claims you cannot make) live in the profile: profile.json -> banned_phrases.
# Spanish entries use unicode escapes (the locale "es" is supported) so the source stays ASCII.
UNIVERSAL_BANNED = [
    ';', '\u2014', '\u2013',
    'excellent', 'amazing', 'impressive', 'excelente', 'incre\u00edble', 'impresionante', 'me encant\u00f3',
    'promptly', 'i would be glad', 'i came across', 'i hope this email', 'i noticed your website', 'your website is',
    'espero que este correo', 'pongo mi servicio', 'con gusto colaboro', 'me pongo a su disposici\u00f3n', 'quise ponerme',
    'vi su informaci\u00f3n',
    'violating', 'out of compliance', 'lawsuit', 'violan', 'incumpl', 'demanda',
    'outdated', 'old-fashioned', 'ugly', 'obsolete', 'poorly designed', 'broken', 'not mobile', 'anticuad', 'desactualizad',
    'fea', 'feo', 'vieja', 'viejo', 'mal dise\u00f1ad', 'no se ve bien',
]
BANNED = UNIVERSAL_BANNED + [b.lower() for b in PROFILE.get('banned_phrases', [])]
PROMISES = re.compile(r'\$|\bcents?\b|centavos|%|\bhours?\b|\bhoras?\b|\bdays?\b|\bd\u00edas?\b|same[- ]day|mismo d\u00eda|'
                      r'\bfast\b|\bquick|r\u00e1pid|calidad|quality|\bbest\b|\bmejor(es)?\b|cheap|barat|guarantee|garantiz', re.I)
GREETING = re.compile(r'^(hola|hello|hi|dear|estimad|buen[oa]s)\b', re.I)
LANG_HINTS = {
    'en': {'the', 'and', 'your', 'of', 'to', 'in', 'for', 'with', 'that', 'is', 'a', 'on'},
    'es': {'de', 'la', 'que', 'el', 'en', 'y', 'los', 'su', 'sus', 'para', 'con', 'las', 'una', 'por'},
}
ENUMERATION = re.compile(PROFILE.get('first_line', {}).get('enumeration_terms', r'(?!x)x'), re.I)
ENUMERATION_MAX = PROFILE.get('first_line', {}).get('enumeration_max', 2)
DROP_SUFFIX = re.compile(r',?\s+(LLC|L\.L\.C\.|INC\.?|INCORPORATED|CORP\.?|CORPORATION|CO\.?|P\.?A\.?|PLLC|LTD\.?)$', re.I)
DEFAULT_GREETING = {'person': 'Hello {first},', 'team': 'Hello {name} team,', 'anonymous': 'Hello,'}


def display_name(raw: str) -> str:
    n = raw.replace('&amp;', '&').strip()
    for _ in range(2):
        n = DROP_SUFFIX.sub('', n).strip(' ,')
    if n.isupper():
        n = ' '.join(w if len(w) <= 3 and w.isalpha() and i == 0 else w.capitalize() for i, w in enumerate(n.split()))
    return n


def evidence_text(camp, dom: str) -> str:
    d = camp / 'evidence' / dom
    return ' '.join(page_text(p.read_text(encoding='utf-8', errors='ignore')) for p in sorted(d.glob('*.html'))) if d.exists() else ''


def banned_hits(text: str) -> list[str]:
    """Banned phrases found in `text` (already lowercased). Single words match whole words, phrases match as substrings."""
    return [b for b in BANNED if ((b in text) if not b.isalpha() else re.search(r'\b' + re.escape(b) + r'\b', text))]


def line_problems(line: str, proof: str, locale: str, site_text: str) -> list[str]:
    """Why a first line can't go out (empty list = it can). The same rules run again in verify.py."""
    p = []
    low = norm(line)
    words = line.split()
    if not 8 <= len(words) <= 50:
        p.append(f'has {len(words)} words (8 to 50)')
    if GREETING.match(line.strip()):
        p.append('starts with a greeting (the greeting is added before the line)')
    for b in banned_hits(low):
        p.append(f"uses '{b}'")
    if len(ENUMERATION.findall(low)) > ENUMERATION_MAX:
        p.append('lists documents or products (the next paragraph already does that)')
    if PROMISES.search(line):
        p.append('talks about price, deadline, speed or quality (that goes later, or not at all)')
    if not proof or len(proof.split()) < 4:
        p.append('the proof is missing (4 to 15 words copied from their site)')
    elif norm(proof) not in site_text:
        p.append('the proof does not appear letter by letter in the saved pages')
    else:
        pw = norm(proof).split()
        runs = {' '.join(pw[i:i + 5]) for i in range(len(pw) - 4)}
        if any(r in low for r in runs):
            p.append('copies 5 words in a row from their site (say it in other words)')
    toks = set(re.findall(r'[^\W\d_]+', low))
    hints = LANG_HINTS.get(locale)
    if hints and len(toks & hints) < 2:
        p.append(f'does not look written in the email language ({locale})')
    return p


def facts_for(lead: dict) -> str:
    r = lead.get('summary', {})
    sig = '\n'.join(f"- {s['label']}: \"{s.get('quote', '')}\"" for s in lead.get('signals', []) if s.get('quote'))
    return (f"Home page: {r.get('home', '')[:380]}\nWho they are: {r.get('about', '')[:300]}\n"
            f"Services or products: {', '.join(r.get('services', [])[:10])}\n{sig}").strip()


def greeting(lead: dict, locale: str) -> str:
    table = {**DEFAULT_GREETING, **(TEMPLATES.get('greeting', {}).get(locale) or TEMPLATES.get('greeting', {}).get(DEFAULT_LOCALE) or {})}
    who = lead.get('contact') or {}
    first = who.get('name', '').split()[0] if who.get('name') else ''
    if first:
        return table['person'].format(first=first)
    if lead.get('name_reliable', True):
        return table['team'].format(name=display_name(lead['name']))
    return table['anonymous']  # the name may be a page title ("Manufacturing"): better no name than a wrong one


def offer_content(lead: dict, sector: dict) -> tuple[str, dict, dict | None]:
    """(offer kind, the offer's subject/block holder, the alternate offer or None): the ladder may have chosen
    an alternate offer (profile offer_ladder.alternates) instead of the sector's own."""
    alt = PROFILE.get('offer_ladder', {}).get('alternates', {}).get(lead.get('offer', ''))
    if alt:
        return lead['offer'], alt, alt
    return sector.get('offer', 'default'), sector, None


def compose(lead: dict, sector: dict, locale: str, first_line: str) -> tuple[str, str, str]:
    """(subject, email body, form message). Same structure for every company; only the first line is theirs."""
    kind, holder, alt = offer_content(lead, sector)
    subject, block = locale_text(holder['subject'], locale), locale_text(holder['block'], locale)
    # A/B/C test of the offer paragraph (variants.json): the only part of the email that varies.
    variant = assign_variant(lead['domain'], lead['sector'], kind)
    options = VARIANTS['offers'][kind][variant]
    offer = options.get(locale) or options[DEFAULT_LOCALE]
    lead['variant'], lead['offer_kind'] = variant, kind
    sign = locale_text(SENDER['signature'], locale)
    link = locale_text((alt or {}).get('link'), locale)
    if link:  # the offer's own page instead of the general business page
        sign = '\n'.join(sign.split('\n')[:-1] + [link])
    body = '\n\n'.join([greeting(lead, locale), first_line, block, *offer, sign, locale_text(SENDER['opt_out'], locale)])
    reply = locale_text(TEMPLATES.get('form_reply_line', {'en': 'My email: {mailbox}'}), locale).format(mailbox=SENDER['from_mailbox'])
    form = '\n\n'.join([first_line, block, offer[0], reply + '\n' + TEMPLATES.get('form_signature', '')]).strip()
    return subject, body, form


HINTS = {'localization': 'Offer: LOCALIZATION of their website. Connect the detail with the people who look for them online in the other language.',
         'new_website': 'Offer: NEW WEBSITE in two languages. Connect the detail with whoever finds them from a phone or in the other language. Never say their site is old or ugly.'}


def write_pending(camp, pending: list[dict], vocab=None) -> None:
    md = ['# First lines still missing', '',
          'Write them yourself, the agent running the skill (no other model, no API). One per company, in '
          '`manual_lines.jsonl` (one JSON line per company), then run `draft.py` again:', '',
          '```', '{"id": "L100001", "first_line": "...", "proof": "4 to 15 words copied as they are from their site"}', '```', '',
          'Rules: references/TEMPLATES.md, section "The first line". Read only what is below; do not open the pages '
          'unless a fact is missing: that way tokens are not wasted.', '']
    for l in pending:
        hint = HINTS.get(l.get('offer'), f"Offer: what their sector gets ({l.get('offer_kind') or l.get('offer', '')}).")
        rare = ', '.join(vocab.rare_words(l['domain'], l['name'], text=facts_for(l))) if vocab else ''
        md += [f"## {l['id']} | {l['name']} | {l['sector_name']} | {l['city'] or l['county']}, {l.get('state', '')} | write in {l['locale']}",
               hint,
               *([f"Your previous line did not pass: {l['failure']}"] if l.get('failure') else []),
               *([f"Words particular to their site (use at least 2): {rare or '(their site has almost nothing of its own: look for a detail in the services)'}"] if vocab else []),
               '', facts_for(l), '']
    (camp / 'FOR_DRAFTING.md').write_text('\n'.join(md), encoding='utf-8')


def main() -> None:
    ap = argparse.ArgumentParser(description='Step 5: assemble the emails; the agent writes the first lines.')
    add_profile_arg(ap)
    ap.add_argument('--campaign', required=True)
    a = ap.parse_args()
    missing = profile_placeholders()
    if missing:
        sys.exit('The active profile still has REPLACE_ME in: ' + ', '.join(missing[:6]) +
                 '\nFinish the onboarding (SKILL.md, "First run") before drafting emails.')
    camp = campaign_dir(a.campaign)
    sectors = {s['id']: s for s in load_sectors()}
    leads = read_jsonl(camp / 'leads.jsonl')
    drafts = {d['id']: d for d in read_jsonl(camp / 'drafts.jsonl')}
    manual = {m['id']: m for m in read_jsonl(camp / 'manual_lines.jsonl')}
    # Where each published email was found. A company already queued loses email_page when score.py runs
    # again: without it verify.py cannot reopen the page and every email fails.
    email_page = {(r['domain'], c['email'].lower()): c['page'] for r in read_jsonl(camp / 'scan.jsonl')
                  for c in r.get('emails') or [] if c.get('email') and c.get('page')}
    pending = []
    vocab = Vocabulary(camp)  # which words are each company's own (quality.py): catches generic lines
    logged = {(r['id'], r['line']) for r in read_jsonl(camp / 'line_rejections.jsonl')}
    # A company already queued is redone only when its line was corrected by hand (manual_lines.jsonl).
    todo = [l for l in leads if l['status'] in ('to_draft', 'form') or (l['status'] == 'queued' and l.get('id') in manual)]
    for n, lead in enumerate(todo, 1):
        sector = sectors[lead['sector']]
        locale = lead.get('site_locale') or DEFAULT_LOCALE
        lead['locale'] = locale
        prev = drafts.get(lead['id'])
        if prev and not prev.get('pending') and lead['id'] not in manual:
            continue
        site_text = evidence_text(camp, lead['domain'])
        line = proof = how = ''
        if lead['id'] in manual:
            m = manual[lead['id']]
            probs = line_problems(m.get('first_line', ''), m.get('proof', ''), locale, site_text)
            # Generic, repeated or a claim about their clients. The repetition rule only looks at companies with a
            # lower id, so the first two lines with a given ending pass and the third has to be reworded.
            before = [d['first_line'] for k, d in drafts.items() if not d.get('pending') and k < lead['id'] and d.get('first_line')]
            probs += quality_problems(m.get('first_line', ''), m.get('proof', ''), display_name(lead['name']), before, vocab, lead['domain'])
            if probs:
                lead['failure'] = 'your line: ' + '; '.join(probs)
                if (lead['id'], m.get('first_line', '')) not in logged:  # every rejection is kept: it measures the agent
                    append_jsonl(camp / 'line_rejections.jsonl', {'id': lead['id'], 'date': dt.datetime.now().isoformat(timespec='seconds'),
                                                                  'line': m.get('first_line', ''), 'reason': probs[0]})
                    logged.add((lead['id'], m.get('first_line', '')))
            else:
                line, proof, how = m['first_line'], m['proof'], 'agent'
        if not line:
            pending.append(lead)
            drafts[lead['id']] = {'id': lead['id'], 'domain': lead['domain'], 'pending': True}
            write_jsonl(camp / 'drafts.jsonl', list(drafts.values()))  # saved as it goes: a cut loses nothing
            print(f'   {n}/{len(todo)} {lead["id"]}: first line missing', flush=True)
            continue
        subject, body, form_msg = compose(lead, sector, locale, line)
        d = {'id': lead['id'], 'domain': lead['domain'], 'name': display_name(lead['name']), 'channel': lead['channel'],
             'to': lead.get('email', ''), 'email_page': (lead.get('email_page') or (prev or {}).get('email_page')
                                                          or email_page.get((lead['domain'], lead.get('email', '').lower()), '')),
             'subject': subject, 'body': body, 'form_message': form_msg, 'first_line': line, 'proof': proof,
             'line_author': how, 'locale': locale, 'sector': lead['sector'], 'city': lead['city'] or lead['county'],
             'state': lead.get('state', ''), 'points': lead['points'], 'forms': lead.get('forms', []),
             'offer': lead.get('offer', ''), 'offer_kind': lead.get('offer_kind', ''), 'variant': lead.get('variant', ''),
             'experiment': VARIANTS.get('experiment', ''), 'pending': False}
        drafts[d['id']] = d
        write_jsonl(camp / 'drafts.jsonl', list(drafts.values()))
        print(f'   {n}/{len(todo)} {lead["id"]}: ready ({how})', flush=True)
    write_jsonl(camp / 'drafts.jsonl', list(drafts.values()))
    write_pending(camp, pending, vocab)
    ok = sum(1 for d in drafts.values() if not d.get('pending'))
    log(camp, f'draft: {ok} drafts ready, {len(pending)} waiting for their first line (FOR_DRAFTING.md)')
    if pending:
        print(f'\n{len(pending)} first lines are missing. Write them in {camp / "manual_lines.jsonl"} following '
              f'{camp / "FOR_DRAFTING.md"} and run this step again.')
        sys.exit(2)


if __name__ == '__main__':
    main()
