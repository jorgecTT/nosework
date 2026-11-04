"""Step 2 - reads each candidate's own website and writes down only what is published there.

For every site (robots.txt respected, a pause between pages) it reads the home page and up to
max_pages_per_site internal pages chosen by their links (contact, about, team, jobs, services, the
alternate-language version, forms) and extracts, without any AI:
  emails      emails published on the site (own domain or a free mailbox), with the page where each one is
  people      named people with their role (owner, founder, manager...), from team pages and schema.org data
  forms       contact forms: page, action, fields, captcha; so a later step can contact them that way
  signals     why they could need you: the buying signals defined in the profile (signals.json), each with
              the page and the sentence that prove it
  size        employees, team size, number of locations, when the site says so (an estimate, never a fact)
  age         founding year from "since 1998", "founded in", "over 20 years", the oldest copyright year
  summary     first paragraphs of the home and about pages, and the service headings: the raw material of the email
The pages are saved as evidence in <campaign>/evidence/<domain>/. Writes <campaign>/scan.jsonl
(resumable: sites already read are skipped).

Usage: python3 scan.py --campaign fl-miami [--max 300] [--threads 6]
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import html as html_lib
import json
import re
import threading
import time
import urllib.parse

from common import (CONFIG, DEFAULT_LOCALE, EXCLUDED_SITE, FREE_MAIL, LISTICLE, LOCALES, PAUSE, PLACEHOLDER_EMAIL, PROFILE,
                    ROOT, SIGNALS, UA, WRONG_INBOX, add_profile_arg, append_jsonl, campaign_dir, decode_cfemail, domain,
                    get, load_sectors, log, page_text, paragraphs, read_jsonl, robots_for)

YEAR = dt.date.today().year
ALT = PROFILE.get('alt_version', {})
REGIONS = json.loads((ROOT / 'references' / 'regions.json').read_text(encoding='utf-8'))['states']
# Page types, found by words in the link. English first; the Spanish words are there for sites in Spanish.
LINK_HINTS = {
    'contact': ['contact', 'contacto', 'get-in-touch', 'reach-us', 'location'],
    'about': ['about', 'nosotros', 'quienes-somos', 'our-story', 'history', 'who-we-are', 'company'],
    'team': ['team', 'staff', 'leadership', 'our-people', 'equipo', 'management', 'doctors', 'providers', 'meet'],
    'services': ['service', 'servicio', 'products', 'productos', 'what-we-do', 'solutions', 'capabilities', 'industries'],
    'jobs': ['career', 'jobs', 'employment', 'join', 'hiring', 'empleo', 'trabaja', 'work-with-us'],
    'documents': ['form', 'patient', 'parent', 'resources', 'download', 'handbook', 'enroll', 'admission', 'policies'],
    'alt_language': ALT.get('link_hints', []),
}
ORDER = ['contact', 'about', 'team', 'services', 'jobs', 'alt_language', 'documents']
# Titles that mark a person as someone who decides. Spanish titles use unicode escapes (the source stays ASCII).
DECISION = re.compile(r'owner|founder|ceo|chief|president|principal|managing|general manager|office manager|practice manager|'
                      r'operations|administrator|due\u00f1|fundador|presidente|gerente general|director', re.I)
UP, LOW = 'A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1', "a-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1'\u2019-"
NAME_RE = re.compile(rf"^(?:(?:dr|mr|mrs|ms)\.?\s+)?([{UP}][{LOW}]+(?:\s+[A-Z]\.)?(?:\s+(?:de\s+la\s+|de\s+|del\s+)?"
                     rf"[{UP}][{LOW}]+){{1,3}})(?:,?\s+(?:md|dds|dmd|cpa|pe|rn|np|dvm|od|dpt|pa-c|mba|jr\.?|sr\.?))*$")
NOT_NAME = re.compile(r'\b(our|the|and|for|with|your|services?|contact|about|team|home|company|group|llc|inc|corp|'
                      r'center|florida|texas|york|street|avenue|suite|read|more|learn|call|view|news|blog|'
                      r'privacy|policy|terms|copyright|meet|welcome|reviews?|testimonials?|careers?|products?|'
                      r'luxury|feedback|pricing|request|inspection|business|sales|springs|gables|beach|park|lakes?|'
                      r'gardens?|heights|repair|install\w*|instalaci\w*|estimate|quote|free|emergency|commercial|'
                      r'residential|customer|success|support|why|how|what|new|best|top|step|into|get|book|'
                      r'schedule|service|plan|care|solutions?|marketing|design|financial|tax|insurance|loans?)\b', re.I)
ROLE_START = re.compile(r'^\W*(?:senior\s+|executive\s+|assistant\s+|associate\s+)?(?:' + '|'.join(
    ['owner', 'co-owner', 'founder', 'co-founder', 'ceo', 'chief', 'president', 'vice president', 'vp', 'principal',
     'managing', 'partner', 'general manager', 'office manager', 'practice manager', 'operations', 'director',
     'administrator', 'manager', 'coordinator', 'head', 'coo', 'cfo', 'cpa', 'due\u00f1', 'fundador', 'presidente', 'gerente',
     'directora', 'administradora', 'socio', 'socia']) + r')', re.I)
SIZE_PATTERNS = [
    (re.compile(r'(?:over|more than|nearly|approximately|about|\+)?\s*(\d{1,3}(?:,\d{3})?)\s*\+?\s+(?:full[- ]time\s+)?'
                r'(?:employees|team members|staff members|professionals|technicians|caregivers|associates|workers|'
                r'empleados|trabajadores|colaboradores|people on our team)', re.I), 'employees'),
    (re.compile(r'team of (?:over |more than )?(\d{1,4})', re.I), 'employees'),
    (re.compile(r'(\d{1,3})\s+(?:locations|offices|branches|clinics|stores|sucursales|oficinas|sedes)', re.I), 'locations'),
]
FOUNDED_PATTERNS = [
    re.compile(r'(?:since|founded in|established in|established|est\.?|founded|desde|fundad[ao] en|en el a\u00f1o)\s+((?:19|20)\d\d)', re.I),
    re.compile(r'((?:19|20)\d\d)\s*[-\u2013]\s*(?:present|today)', re.I),
]
YEARS_PATTERN = re.compile(r'(?:over|more than|nearly|for|m\u00e1s de)?\s*(\d{1,3})\+?\s+(?:years|a\u00f1os)\s+(?:of experience|in business|'
                           r'serving|de experiencia|sirviendo|experience)', re.I)
COPYRIGHT = re.compile(r'(?:\u00a9|&copy;|copyright)\s*((?:19|20)\d\d)', re.I)
CAPTCHA = [('recaptcha', r'g-recaptcha|recaptcha/api\.js|grecaptcha'), ('hcaptcha', r'hcaptcha'),
           ('turnstile', r'cf-turnstile|challenges\.cloudflare\.com/turnstile')]
FORM_PROVIDERS = [('jotform', r'jotform'), ('typeform', r'typeform'), ('hubspot', r'hsforms|hbspt\.forms'),
                  ('google_forms', r'docs\.google\.com/forms'), ('wix', r'wixforms|wix-forms'), ('formstack', r'formstack'),
                  ('cognito', r'cognitoforms'), ('gravity', r'gform_'), ('contact_form_7', r'wpcf7'),
                  ('elementor', r'elementor-form'), ('wpforms', r'wpforms'), ('ninja', r'nf-form'), ('squarespace', r'sqs-block-form')]
OLD_TECH = [('Flash', r'\.swf\b|application/x-shockwave-flash'), ('jQuery 1.x', r'jquery[.-]?1\.\d+(\.\d+)?(\.min)?\.js'),
            ('table layout', r'(?is)<table[^>]+(?:width=["\']?\d{3,}|cellpadding)'),
            ('frames', r'(?is)<frameset|<frame\b'), ('conditional IE', r'<!--\[if (lt )?IE')]
NAME_FILLER = {'the', 'and', 'of', 'inc', 'llc', 'corp', 'co', 'company', 'group', 'services', 'service', 'center',
               'south', 'north', 'usa', 'us', 'de', 'la', 'el', 'y', 'pa', 'llp', 'pllc'}
ORG_TYPE = re.compile(r'Organization|LocalBusiness|Corporation|Store|Business|Service|Bakery|Restaurant|Contractor|'
                      r'Clinic|Dentist|Physician|Agency|Company|Manufacturer|Wholesale|Plumber|Electrician|Roofing|HVAC', re.I)
lock = threading.Lock()
SECTOR_KEYS = {s['id']: s.get('keywords', []) for s in load_sectors()}


def internal_links(base: str, html: str) -> dict[str, list[str]]:
    site = domain(base)
    found = {k: [] for k in LINK_HINTS}
    for href in re.findall(r'href=["\']([^"\'#]+)', html, re.I):
        url = urllib.parse.urljoin(base, href.strip())
        if domain(url) != site or re.search(r'\.(pdf|jpe?g|png|gif|zip|docx?|xlsx?|mp4)(\?|$)', url, re.I):
            continue
        low = url.lower()
        for kind, hints in LINK_HINTS.items():
            if any(h in low for h in hints) and url not in found[kind]:
                found[kind].append(url)
    return found


def emails_on(site: str, html: str) -> list[str]:
    out = []
    raw = decode_cfemail(html).replace('&#64;', '@').replace('&#x40;', '@').replace('%40', '@')
    raw = re.sub(r'\s*\[\s*at\s*\]\s*', '@', raw, flags=re.I)
    for e in re.findall(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}', raw, re.I):
        e = e.lower().strip('.').removeprefix('mailto:')
        if PLACEHOLDER_EMAIL.search(e) or re.search(r'\.(png|jpe?g|webp|gif|svg|css|js)$', e) or len(e) > 60:
            continue
        # "555-123-4567info@example.com": a phone number glued in front of the address.
        e = re.sub(r'^\(?\d[\d\-. ()]{3,}\d(?=[a-z])', '', e)
        e_dom = e.split('@')[1]
        if (e_dom == site or e_dom.endswith('.' + site) or site.endswith('.' + e_dom) or e_dom in FREE_MAIL) and e not in out:
            out.append(e)
    # A clean address also found on the site wins over a longer one that only adds junk in front of it.
    return [e for e in out if not any(o != e and e.endswith(o) and not e[:-len(o)].endswith('.') for o in out)]


def text_chunks(html: str) -> list[str]:
    """The page as short pieces of visible text, in order: names and roles sit in neighbouring pieces."""
    html = re.sub(r'(?is)<(script|style|noscript|svg|nav|footer)\b.*?</\1>', ' ', html)
    pieces = re.split(r'(?is)<[^>]+>', html)
    return [c for c in (re.sub(r'\s+', ' ', p).strip(' |\u00b7\u2022-\u2013') for p in pieces) if c and len(c) < 160]


PHRASE_PERSON = re.compile(rf"(?<![\w])([A-Z][{LOW}]+(?: [A-Z][{LOW}]+){{1,2}}) ?, ((?i:Owner|Founder|Co-Founder|President|CEO|"
                           r"General Manager|Office Manager|Practice Manager|Director|Administrator|Principal|Due\u00f1[oa]|Fundador[a]?|Gerente))")


def people_on(html: str, page: str) -> list[dict]:
    people = []

    def add(name: str, role: str, how: str):
        name, role = name.strip(), role.strip()[:80]
        if (NOT_NAME.search(name) or len(name) > 40 or len(name.split()) < 2 or any(p['name'] == name for p in people)
                or (role and not ROLE_START.search(role))):
            return
        people.append({'name': name, 'role': role, 'page': page, 'how': how})

    for block in re.findall(r'(?is)<script[^>]+ld\+json[^>]*>(.*?)</script>', html):
        try:
            data = json.loads(block)
        except Exception:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                if item.get('@type') == 'Person' and isinstance(item.get('name'), str):
                    add(item['name'], str(item.get('jobTitle', '')), 'schema.org')
                stack += [v for v in item.values() if isinstance(v, (dict, list))]
            elif isinstance(item, list):
                stack += item
    chunks = text_chunks(html)
    for i, c in enumerate(chunks):
        m = NAME_RE.match(c)
        if not m:
            continue
        role = next((c2 for c2 in chunks[i + 1:i + 3] if len(c2.split()) <= 8 and ROLE_START.search(c2)), '')
        if role:
            add(m.group(1), role, 'team page')
    for m in PHRASE_PERSON.finditer(re.sub(r'<[^>]+>', '\n', html)):  # tags become line breaks: a name never joins the heading before it
        add(m.group(1), m.group(2), 'phrase')
    return people[:12]


def forms_on(html: str, page: str) -> list[dict]:
    forms = []
    for attrs, body in re.findall(r'(?is)<form\b([^>]*)>(.*?)</form>', html):
        fields = re.findall(r'(?is)<(?:input|textarea|select)\b[^>]*\bname=["\']([^"\']+)', body)
        types = [t.lower() for t in re.findall(r'(?is)<input\b[^>]*\btype=["\']([^"\']+)', body)]
        has_text = bool(re.search(r'(?i)<textarea', body))
        low_fields = ' '.join(fields).lower()
        if re.search(r'role=["\']search|search', attrs, re.I) or set(fields) <= {'s', 'q', 'search', 'query'}:
            continue
        if not has_text and 'email' in ' '.join(types) + low_fields and len(fields) <= 3:
            continue  # newsletter sign-up, not a contact form
        if not has_text and not re.search(r'message|comment|mensaje|inquiry|details', low_fields):
            continue
        action = re.search(r'action=["\']([^"\']*)', attrs, re.I)
        method = re.search(r'method=["\']([^"\']*)', attrs, re.I)
        forms.append({'page': page, 'action': urllib.parse.urljoin(page, action.group(1)) if action and action.group(1) else page,
                      'method': (method.group(1) if method else 'get').lower(), 'fields': fields[:25],
                      'captcha': next((n for n, p in CAPTCHA if re.search(p, html, re.I)), ''),
                      'provider': next((n for n, p in FORM_PROVIDERS if re.search(p, attrs + body, re.I)), 'html')})
    for name, pat in FORM_PROVIDERS[:7]:  # forms embedded from another service (iframe or script)
        m = re.search(r'(?is)<(?:iframe|script)\b[^>]*src=["\']([^"\']*' + pat + r'[^"\']*)', html)
        if m and not any(f['provider'] == name for f in forms):
            forms.append({'page': page, 'action': m.group(1), 'method': 'external', 'fields': [],
                          'captcha': next((n for n, p in CAPTCHA if re.search(p, html, re.I)), ''), 'provider': name})
    return forms


def site_health(base: str, home: str, pages: list[tuple]) -> dict:
    """How dated the site is, from its own pages (no AI, one extra request for the sitemap). Each sign keeps
    its proof. Only used by the offer rule `site_dated`; never said to the company as a criticism."""
    signs = []
    if not re.search(r'(?is)<meta[^>]+name=["\']viewport', home):
        signs.append({'sign': 'not mobile friendly', 'proof': 'the home page has no <meta name="viewport">'})
    years = [int(y) for _, _, h in pages for y in COPYRIGHT.findall(h) if 1995 <= int(y) <= YEAR]
    if years and max(years) <= YEAR - 5:
        signs.append({'sign': 'not updated', 'proof': f'the latest copyright year on the site is {max(years)}'})
    if base.startswith('http://'):
        signs.append({'sign': 'no HTTPS', 'proof': f'the site opens on {base}'})
    if not re.search(r'(?is)<meta[^>]+name=["\']description["\'][^>]+content=["\'][^"\']{20,}', home):
        signs.append({'sign': 'no meta description', 'proof': 'the home page has no meta description'})
    if not re.search(r'(?is)<h1\b', home):
        signs.append({'sign': 'no main heading', 'proof': 'the home page has no <h1>'})
    wp = re.search(r'(?is)<meta[^>]+name=["\']generator["\'][^>]+content=["\']WordPress (\d+)\.(\d+)', home)
    if wp and (int(wp.group(1)), int(wp.group(2))) < (6, 0):
        signs.append({'sign': 'old WordPress', 'proof': f'generator WordPress {wp.group(1)}.{wp.group(2)}'})
    for label, pat in OLD_TECH:
        if re.search(pat, home):
            signs.append({'sign': f'old technology: {label}', 'proof': label})
            break
    st, body, _ = get(urllib.parse.urljoin(base, '/sitemap.xml'))
    st_idx, _, _ = (st, body, '') if st == 200 else get(urllib.parse.urljoin(base, '/sitemap_index.xml'))
    if st != 200 and st_idx != 200:
        signs.append({'sign': 'no sitemap', 'proof': f'/sitemap.xml answers {st}'})
    return {'signs': signs, 'count': len(signs), 'dated': len(signs) >= 3}


def org_name(home: str, title: str, site: str) -> str:
    """The company's own name: og:site_name, then schema.org Organization, then the part of the <title> that
    matches the domain. Search engines only give the page title ("Wholesale bakery | Miami"), never the name."""
    m = re.search(r'(?is)<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\']([^"\']{2,80})', home) or \
        re.search(r'(?is)<meta[^>]+content=["\']([^"\']{2,80})["\'][^>]+property=["\']og:site_name', home)
    if m:
        og = html_lib.unescape(m.group(1)).strip()
        parts = [x.strip() for x in re.split(r'\s[|\-\u2013\u00b7:]\s', og) if x.strip()]
        stem0 = re.sub(r'[^a-z0-9]', '', site.split('.')[0])
        best = next((x for x in parts if re.sub(r'[^a-z0-9]', '', x.lower())[:5] in stem0), parts[0] if parts else og)
        return re.sub(r'\s+(site|website|official site|home)$', '', best, flags=re.I)
    for block in re.findall(r'(?is)<script[^>]+ld\+json[^>]*>(.*?)</script>', home):
        for t, n in re.findall(r'"@type"\s*:\s*"(Organization|LocalBusiness|Corporation|[A-Za-z]*Store|Bakery|Restaurant|'
                               r'[A-Za-z]*Business|[A-Za-z]*Service)"[^{}]*?"name"\s*:\s*"([^"]{2,80})"', block):
            return html_lib.unescape(n).strip()
    stem = re.sub(r'[^a-z0-9]', '', site.split('.')[0])
    parts = [p.strip() for p in re.split(r'\s[|\-\u2013\u00b7:]\s|\s[|\u2013\u00b7]', html_lib.unescape(title)) if p.strip()]
    for p in parts:
        flat = re.sub(r'[^a-z0-9]', '', p.lower())
        if flat and (flat in stem or stem in flat or flat[:6] == stem[:6]):
            return p
    return ''


def name_matches_domain(name: str, site: str) -> bool:
    """True when the name and the domain share a distinctive piece ("Galaxy Bakery" / galaxybakery.com).
    If not, the name may be a page title ("Manufacturing") and the email greets without it."""
    stem = re.sub(r'[^a-z0-9]', '', site.split('.')[0])
    words = [w for w in re.findall(r'[a-z0-9]+', name.lower()) if len(w) >= 3 and w not in NAME_FILLER]
    initials = ''.join(w[0] for w in re.findall(r'[a-z0-9]+', name.lower()))
    return any(w[:5] in stem for w in words) or (len(initials) >= 2 and stem.startswith(initials))


def in_region(pages: list[tuple], state: str, county: str, city: str) -> bool:
    """The site says where it is: the state's name or code next to a city, the county, or the city.
    Search results bring companies from anywhere (an exporter overseas showed up for a local search)."""
    state_name = REGIONS.get(state, {}).get('name', state).lower()
    text = ' '.join(page_text(h) for _, _, h in pages)
    keys = [state_name, county.lower().replace(' county', ''), city.lower()]
    return any(k and k in text for k in keys) or bool(re.search(r'\b' + state.lower() + r'\s+\d{5}\b', text))


def name_on_site(name: str, pages: list[tuple], site: str) -> bool:
    """The business name (a distinctive word of it) is on its own site, or in its domain: proof the site is theirs."""
    words = [w for w in re.findall(r"[^\W_]+(?:'[^\W_]+)?", name.lower()) if len(w) >= 3 and w not in NAME_FILLER]
    if not words:
        return True
    text = ' '.join(page_text(h) for _, _, h in pages[:3])
    flat = site.replace('-', '')
    return any(w in text or w in flat for w in words)


def first_sentence_with(texts: list[str], keys: list[str], max_words: int = 30, patterns: list[str] | None = None) -> str:
    rx = re.compile('|'.join(patterns), re.I) if patterns else None
    for block in texts:
        for s in re.split(r'(?<=[.!?])\s+', block):
            if len(s.split()) >= 6 and (any(k in s for k in keys) or (rx and rx.search(s))):
                return ' '.join(s.split()[:max_words])
    return ''


def _ld_items(html: str):
    for block in re.findall(r'(?is)<script[^>]+ld\+json[^>]*>(.*?)</script>', html):
        try:
            data = json.loads(block.strip())
        except Exception:
            continue
        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack += item
            elif isinstance(item, dict):
                yield item
                stack += [v for v in item.values() if isinstance(v, (dict, list))]


def org_facts(pages: list[tuple]) -> dict:
    """What the company itself declares for search engines (schema.org Organization / LocalBusiness, the data
    extruct reads): number of employees, founding date, founders, email, phone. Taken from extruct's idea,
    written with the standard library."""
    out = {'employees': None, 'founded': None, 'founders': [], 'email': '', 'phone': ''}
    for _, link, html in pages:
        for it in _ld_items(html):
            types = it.get('@type', '')
            types = ' '.join(types) if isinstance(types, list) else str(types)
            if not ORG_TYPE.search(types):
                continue
            emp = it.get('numberOfEmployees')
            if isinstance(emp, dict):
                emp = emp.get('value') or emp.get('maxValue') or emp.get('minValue')
            if out['employees'] is None and str(emp or '').replace(',', '').isdigit():
                out['employees'] = int(str(emp).replace(',', ''))
            fd = re.match(r'((?:19|20)\d\d)', str(it.get('foundingDate', '')))
            if fd and not out['founded'] and int(fd.group(1)) <= YEAR:
                out['founded'] = int(fd.group(1))
            founders = it.get('founder') or it.get('founders') or []
            for f in founders if isinstance(founders, list) else [founders]:
                name = f.get('name') if isinstance(f, dict) else f if isinstance(f, str) else ''
                if name and name not in out['founders']:
                    out['founders'].append(name)
            if not out['email'] and isinstance(it.get('email'), str):
                out['email'] = it['email'].lower().removeprefix('mailto:').strip()
                out['email_page'] = link
            if not out['phone'] and isinstance(it.get('telephone'), str):
                out['phone'] = it['telephone']
    return out


def size_band(n: int | None) -> str:
    return ('unknown' if n is None else 'micro' if n < 10 else 'small' if n < 50 else 'medium' if n < 250 else 'large')


def size_and_age(pages: list[tuple], people: list[dict], org: dict | None = None) -> tuple[dict, dict]:
    text = ' '.join(page_text(h) for _, _, h in pages)
    size = {'employees': None, 'locations': None, 'people_on_site': len(people), 'quote': ''}
    for pat, field in SIZE_PATTERNS:
        m = pat.search(text)
        if m and size[field] is None:
            n = int(m.group(1).replace(',', ''))
            if 1 < n < 200000:
                size[field] = n
                size['quote'] = size['quote'] or ' '.join(text[max(0, m.start() - 60):m.end() + 20].split())
    if org and org.get('employees'):
        size['employees'], size['quote'] = org['employees'], 'the company declares it on its site (schema.org numberOfEmployees)'
    n = size['employees'] or (size['people_on_site'] if size['people_on_site'] >= 3 else None)
    size['band'] = size_band(n)
    if size['locations'] and size['locations'] >= 3 and size['band'] in ('unknown', 'micro'):
        size['band'] = 'multi_site'
    age = {'founded': None, 'how': ''}
    raw = ' '.join(h for _, _, h in pages)
    if org and org.get('founded'):
        age = {'founded': org['founded'], 'how': 'the company declares it on its site (schema.org foundingDate)'}
    for pat in ([] if age['founded'] else FOUNDED_PATTERNS):
        m = pat.search(text)
        if m and 1900 <= int(m.group(1)) <= YEAR:
            age = {'founded': int(m.group(1)), 'how': ' '.join(text[max(0, m.start() - 40):m.end() + 10].split())}
            break
    if not age['founded']:
        m = YEARS_PATTERN.search(text)
        if m and 0 < int(m.group(1)) < 120:
            age = {'founded': YEAR - int(m.group(1)), 'how': ' '.join(m.group(0).split()) + ' (approximate)'}
    years = [int(y) for y in COPYRIGHT.findall(raw) if 1995 <= int(y) <= YEAR]
    age['oldest_copyright'] = min(years) if years else None
    return size, age


def summary(pages: list[tuple]) -> dict:
    out = {'home': '', 'about': '', 'services': []}
    for kind, _, html in pages:
        paras = paragraphs(html, 8)
        if kind == 'home' and not out['home']:
            out['home'] = ' '.join(paras[:3])[:700]
        if kind == 'about' and not out['about']:
            out['about'] = ' '.join(paras[:3])[:700]
        if kind in ('services', 'home'):
            for h in re.findall(r'(?is)<h[2-4]\b[^>]*>(.*?)</h[2-4]>', html):
                t = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', h)).strip()
                if 2 <= len(t.split()) <= 7 and t not in out['services'] and not NOT_NAME.fullmatch(t):
                    out['services'].append(t)
    out['services'] = out['services'][:10]
    return out


def _phrase_quote(text: str, phrases: list[str]) -> str:
    for phrase in phrases:
        i = text.find(phrase)
        if i >= 0:
            words = text[:i].split()[-6:] + phrase.split() + text[i + len(phrase):].split()[:8]
            return ' '.join(words[:25])
    return ''


def detect_signals(sector_id: str, pages: list[tuple], has_alt: bool, defs: list[dict] | None = None) -> list[dict]:
    """The profile's buying signals (signals.json) found on these pages. Each hit keeps the page and the sentence
    that prove it. Signals are evaluated in file order, so one can `require` an earlier one."""
    defs = SIGNALS if defs is None else defs
    texts = [(kind, link, paragraphs(html), html) for kind, link, html in pages]
    found, out = set(), []
    for sig in defs:
        if any(r not in found for r in sig.get('requires', [])):
            continue
        if sig.get('needs_absent') == 'alt_version' and has_alt:
            continue
        hit = None
        kind = sig.get('kind', 'text')
        allowed = sig.get('page_types')
        if kind == 'text' and (sig.get('terms') or sig.get('patterns') or sig.get('phrases')):
            for pkind, link, paras, html in texts:
                if allowed and pkind not in allowed:
                    continue
                q = first_sentence_with(paras, [t.lower() for t in sig.get('terms', [])], patterns=sig.get('patterns'))
                if not q and sig.get('phrases'):
                    q = _phrase_quote(page_text(html), [p.lower() for p in sig['phrases']])
                if q:
                    hit = {'page': link, 'quote': q}
                    break
        elif kind == 'sector_keywords':
            keys = [k.lower() for k in SECTOR_KEYS.get(sector_id, [])]
            for pkind, link, paras, _ in texts:
                q = first_sentence_with(paras, keys)
                if q:
                    hit = {'page': link, 'quote': q}
                    break
        elif kind == 'pdf_links':
            pdfs = sorted({p for _, _, h in pages for p in re.findall(r'href=["\']([^"\']+\.pdf)', h, re.I)})
            skip = re.compile('|'.join(sig['exclude_patterns']), re.I) if sig.get('exclude_patterns') else None
            kept = [p for p in pdfs if not (skip and skip.search(p))]
            if kept:
                hit = {'detail': f'{len(kept)} linked PDF documents', 'example': kept[0][-80:]}
        elif sig.get('requires'):
            hit = {}
        if hit is not None:
            found.add(sig['id'])
            out.append({'id': sig['id'], 'label': sig.get('label', sig['id']), 'points': sig.get('points', 0), **hit})
    return out


def site_locale(home: str) -> str:
    m = re.search(r'<html[^>]+lang=["\']([a-zA-Z]{2})', home, re.I)
    code = m.group(1).lower() if m else ''
    return code if code in LOCALES else DEFAULT_LOCALE


def has_alt_version(raw_lower: str, home: str) -> bool:
    lang = ALT.get('html_lang')
    return any(k.lower() in raw_lower for k in ALT.get('markers', [])) or bool(
        lang and re.search(rf'<html[^>]+lang=["\']{re.escape(lang)}', home, re.I))


def scan(cand: dict, evid_root) -> dict:
    base = cand['site']
    row = {**cand, 'domain': domain(base), 'read_status': '', 'read_date': time.strftime('%Y-%m-%d')}
    rp = robots_for(base)
    if rp and not rp.can_fetch(UA, base):
        return {**row, 'read_status': 'robots.txt does not allow reading it'}
    status, home, final = get(base)
    if status != 200 or not home:
        return {**row, 'read_status': f'home page answers {status}'}
    if domain(final) != row['domain']:
        row['final_domain'] = domain(final)
        a_, b_ = row['domain'].split('.')[0], domain(final).split('.')[0]
        if a_[:5] != b_[:5] and a_ not in b_ and b_ not in a_:
            return {**row, 'read_status': f'redirects to another domain ({domain(final)})'}
        base = final
    title = re.search(r'(?is)<title[^>]*>(.*?)</title>', home)
    row['title'] = re.sub(r'\s+', ' ', title.group(1)).strip()[:150] if title else ''
    if EXCLUDED_SITE.search(row['title']) or EXCLUDED_SITE.search(domain(final)):
        return {**row, 'read_status': 'excluded (matches the profile exclude_site_patterns)'}
    if LISTICLE.search(row['title']) and LISTICLE.search(cand['name']):
        return {**row, 'read_status': 'is a list or a directory, not a company'}
    real = org_name(home, row['title'], domain(final))
    if real and (cand.get('source', '').startswith('brave') or not cand['name']):
        row['search_name'], row['name'] = cand['name'], real
        cand = {**cand, 'name': real}
    pages, used = [('home', base, home)], {base}
    links = internal_links(base, home)
    for kind in ORDER:
        if len(pages) >= CONFIG['max_pages_per_site']:
            break
        for link in links[kind][:1 if kind != 'contact' else 2]:
            if link in used or (rp and not rp.can_fetch(UA, link)):
                continue
            used.add(link)
            time.sleep(PAUSE)
            st, html, _ = get(link)
            if st == 200 and html:
                pages.append((kind, link, html))
    d = evid_root / row['domain']
    d.mkdir(parents=True, exist_ok=True)
    with (d / 'urls.txt').open('w', encoding='utf-8') as fh:
        for i, (kind, link, html) in enumerate(pages):
            (d / f'{i}_{kind}.html').write_text(html, encoding='utf-8')
            fh.write(f'{i}_{kind}.html\t{link}\n')
    site = domain(base)
    emails = []
    for kind, link, html in pages:
        for e in emails_on(site, html):
            if not any(c['email'] == e for c in emails):
                emails.append({'email': e, 'page': link, 'wrong_inbox': bool(WRONG_INBOX.match(e.split('@')[0]))})
    if cand.get('osm_email') and not any(c['email'] == cand['osm_email'].lower() for c in emails):
        row['email_only_in_osm'] = cand['osm_email'].lower()  # not published on the site: never used
    org = org_facts(pages)
    if org['email'] and not any(c['email'] == org['email'] for c in emails) and emails_on(site, org['email']):
        emails.append({'email': org['email'], 'page': org['email_page'],
                       'wrong_inbox': bool(WRONG_INBOX.match(org['email'].split('@')[0]))})
    people = [{'name': f, 'role': 'Founder', 'page': base, 'how': 'schema.org'} for f in org['founders']
              if len(f.split()) >= 2 and not NOT_NAME.search(f)]
    for kind, link, html in pages:
        for p in people_on(html, link):
            if not any(q['name'] == p['name'] for q in people):
                people.append(p)
    for p in people:  # an email that carries the person's name is that person's
        first, last = p['name'].lower().split()[0], p['name'].lower().split()[-1]
        p['email'] = next((c['email'] for c in emails if first in c['email'].split('@')[0] or last in c['email'].split('@')[0]), '')
        p['decides'] = bool(DECISION.search(p['role']))
    forms = []
    for kind, link, html in pages:
        for f in forms_on(html, link):
            if not any(g['action'] == f['action'] for g in forms):
                forms.append(f)
    raw = ' '.join(h for _, _, h in pages).lower()
    has_alt = has_alt_version(raw, home)
    size, age = size_and_age(pages, people, org)
    phones = ([org['phone']] if org['phone'] else []) + sorted(set(re.findall(r'href=["\']tel:([+\d\-().\s]{7,20})', ' '.join(h for _, _, h in pages))))
    sigs = detect_signals(cand['sector'], pages, has_alt)
    return {**row, 'read_status': 'ok', 'name_on_site': name_on_site(cand['name'], pages, site),
            'name_reliable': name_matches_domain(row['name'], site),
            'in_region': in_region(pages, cand['state'], cand['county'], cand.get('city', '')),
            'pages': [{'type': k, 'url': l} for k, l, _ in pages], 'emails': emails,
            'people': people, 'forms': forms, 'phones': phones[:3], 'site_locale': site_locale(home),
            'has_alt_version': has_alt, 'signals': sigs, 'size': size, 'age': age,
            'site_health': site_health(base, home, pages), 'summary': summary(pages)}


def main() -> None:
    ap = argparse.ArgumentParser(description='Step 2: read each candidate site (robots.txt respected) and extract what it publishes.')
    add_profile_arg(ap)
    ap.add_argument('--campaign', required=True)
    ap.add_argument('--max', type=int, default=0, help='how many new sites to read in this run (0 = all)')
    ap.add_argument('--threads', type=int, default=CONFIG['scan_threads'])
    a = ap.parse_args()
    camp = campaign_dir(a.campaign)
    out = camp / 'scan.jsonl'
    done = {r['domain'] for r in read_jsonl(out)}
    todo = [c for c in read_jsonl(camp / 'candidates.jsonl') if domain(c['site']) not in done]
    if a.max:
        todo = todo[:a.max]
    log(camp, f'scan: {len(todo)} sites to read ({len(done)} already read)')
    evid = camp / 'evidence'
    counts = {'ok': 0, 'other': 0}

    def work(c):
        try:
            r = scan(c, evid)
        except Exception as e:  # one broken site never stops the run
            r = {**c, 'domain': domain(c['site']), 'read_status': f'error {type(e).__name__}: {str(e)[:80]}'}
        with lock:
            append_jsonl(out, r)
            counts['ok' if r['read_status'] == 'ok' else 'other'] += 1
            n = counts['ok'] + counts['other']
            if n % 25 == 0:
                log(camp, f'   {n}/{len(todo)} read ({counts["ok"]} fine)')

    with cf.ThreadPoolExecutor(a.threads) as ex:
        list(ex.map(work, todo))
    log(camp, f'scan finished: {counts["ok"]} read fine, {counts["other"]} not read (down, blocked or excluded)')


if __name__ == '__main__':
    main()
