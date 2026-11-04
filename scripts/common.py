"""Shared pieces of nosework: paths, the active profile, HTTP with robots.txt, text extraction, the contact guard.

Standard library only, so any agent (Claude, Codex, Gemini, or a human) can run the scripts with plain
`python3` and nothing to install. Every script imports from here.

The active profile (everything company-specific) is chosen with `--profile <dir>` on any script, or the
NOSEWORK_PROFILE environment variable. The default is profiles/example-translation-agency.
Working data goes to <repo>/data/<campaign>/ (or $NOSEWORK_DATA).
"""
import csv
import html as html_lib
import json
import os
import re
import ssl
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path

try:  # POSIX only; on Windows the id and variant locks are skipped (single agent at a time)
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE = ROOT / 'profiles' / 'example-translation-agency'
PLACEHOLDER_MARK = 'REPLACE_ME'


class ProfileError(Exception):
    """The active profile is missing or malformed."""


def _arg_profile() -> str:
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == '--profile' and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith('--profile='):
            return a.split('=', 1)[1]
    return os.environ.get('NOSEWORK_PROFILE', '')


def resolve_profile_dir(value: str = '') -> Path:
    if not value:
        return DEFAULT_PROFILE
    for cand in (Path(value).expanduser(), ROOT / value, ROOT / 'profiles' / value):
        if (cand / 'profile.json').exists():
            return cand.resolve()
    raise ProfileError(f'no profile.json found for --profile {value!r} (looked in the path given and in profiles/)')


def _read_json(path: Path, required: bool = True):
    if not path.exists():
        if required:
            raise ProfileError(f'{path} is missing')
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        raise ProfileError(f'{path} is not valid JSON: {e}')


def load_profile(directory: Path) -> dict:
    """All the profile files in one dict. Keys that start with '_' are documentation and are ignored."""
    sectors = _read_json(directory / 'sectors.json')
    variants = _read_json(directory / 'variants.json')
    if not isinstance(sectors.get('sectors'), list):
        raise ProfileError(f"{directory / 'sectors.json'}: 'sectors' must be a list")
    if not isinstance(variants.get('offers'), dict):
        raise ProfileError(f"{directory / 'variants.json'}: 'offers' must be an object")
    signals = _read_json(directory / 'signals.json', required=False) or {'signals': []}
    templates = _read_json(directory / 'templates.json', required=False) or {}
    return {'dir': directory, 'profile': _read_json(directory / 'profile.json'), 'sectors': sectors,
            'variants': variants, 'signals': signals.get('signals', []), 'templates': templates}


def placeholders(obj, path: str = '') -> list[str]:
    """Paths of every string in the profile that still holds the REPLACE_ME marker (the blank template)."""
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            found += placeholders(v, f'{path}.{k}' if path else k)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found += placeholders(v, f'{path}[{i}]')
    elif isinstance(obj, str) and PLACEHOLDER_MARK in obj:
        found.append(path)
    return found


PROFILE_ERROR = ''
try:
    PROFILE_DIR = resolve_profile_dir(_arg_profile())
    _LOADED = load_profile(PROFILE_DIR)
except ProfileError as e:
    PROFILE_ERROR = str(e)
    PROFILE_DIR = DEFAULT_PROFILE
    _LOADED = {'dir': PROFILE_DIR, 'profile': {}, 'sectors': {'sectors': []}, 'variants': {'offers': {}},
               'signals': [], 'templates': {}}
    if Path(sys.argv[0]).name != 'doctor.py':
        sys.exit(f'nosework: profile problem: {PROFILE_ERROR}')

PROFILE = _LOADED['profile']
SECTORS_DOC = _LOADED['sectors']
VARIANTS = _LOADED['variants']
SIGNALS = _LOADED['signals']
TEMPLATES = _LOADED['templates']

def profile_placeholders() -> list[str]:
    """Where the active profile still says REPLACE_ME (the blank template). Drafting refuses to run on those."""
    return (placeholders(PROFILE, 'profile') + placeholders(SECTORS_DOC, 'sectors') + placeholders(VARIANTS, 'variants')
            + placeholders(TEMPLATES, 'templates'))


CONFIG = {**json.loads((ROOT / 'config.json').read_text(encoding='utf-8')), **PROFILE.get('settings', {})}
DATA = Path(os.environ.get('NOSEWORK_DATA') or ROOT / CONFIG['work_dir']).expanduser()
UA = PROFILE.get('user_agent') or CONFIG['default_user_agent']
PAUSE = CONFIG['pause_per_site_seconds']
SENDER = PROFILE.get('sender', {})
LOCALES = PROFILE.get('locales') or ['en']
DEFAULT_LOCALE = PROFILE.get('default_locale') or LOCALES[0]

CTX = ssl.create_default_context()
CTX_UNVERIFIED = ssl.create_default_context()  # only for reading public pages whose certificate is broken
CTX_UNVERIFIED.check_hostname = False
CTX_UNVERIFIED.verify_mode = ssl.CERT_NONE

FREE_MAIL = {'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'aol.com', 'icloud.com', 'live.com',
             'msn.com', 'att.net', 'comcast.net', 'bellsouth.net', 'verizon.net', 'me.com'}
PLACEHOLDER_EMAIL = re.compile(r'^(user|name|email|your(name|email)?|example|test|john|jane|johndoe|info@example)@|'
                               r'@(domain|example|email|yourdomain|yoursite|company|sentry[\w.-]*|wixpress|'
                               r'.*\.wix\.com|godaddy|squarespace|mysite)\.', re.I)
# Inboxes that never buy anything. A row with only these goes to the forms list or out.
WRONG_INBOX = re.compile(r'^(hr|jobs?|careers?|recruit\w*|employment|hiring|talent|payroll|privacy|legal|'
                         r'compliance|webmaster|noreply|no-reply|donotreply|do-not-reply|press|media|abuse|'
                         r'unsubscribe|billing|invoices?|ap|accounts?payable|security|dmca)\b', re.I)


def _regex_or_never(patterns: list[str]) -> re.Pattern:
    return re.compile('|'.join(patterns), re.I) if patterns else re.compile(r'(?!x)x')


# Competitors and conflicts of interest: patterns come from the profile (exclude_site_patterns).
EXCLUDED_SITE = _regex_or_never(PROFILE.get('exclude_site_patterns', []))
# Directories and platforms: never the source of a business's own site.
DIRECTORIES = re.compile(r'sunbiz|bizapedia|opencorporates|yelp|linkedin|facebook|instagram|yellowpages|bbb\.org|'
                         r'mapquest|manta|chamberofcommerce|dnb\.com|zoominfo|google\.|apple\.com|nextdoor|'
                         r'indeed|glassdoor|x\.com|twitter|tiktok|youtube|wikipedia|angi|houzz|'
                         r'trustpilot|birdeye|cylex|hotfrog|brownbook|allbiz|tupalo|doordash|ubereats|grubhub|'
                         r'opentable|tripadvisor|healthgrades|zocdoc|vitals\.com|webmd|realtor\.com|zillow|'
                         r'amazon\.|ebay\.|etsy\.|shopify\.com|wix\.com|squarespace\.com|godaddysites|bluecart|'
                         r'thomasnet|alibaba|made-in-china|indiamart|kompass|buyerzone|expertise\.com|clutch\.co|upcity|'
                         r'bark\.com|homeadvisor|porch\.com|reddit|quora|medium\.com|crunchbase|f6s|'
                         r'ensun|datanyze|rocketreach|apollo\.io|seamless\.ai|signalhire|leadiq|lusha', re.I)
# Search results that are lists or articles about companies, not a company ("Top 23 Food Manufacturers").
LISTICLE = re.compile(r'\b(top|best|leading|largest)\s+\d+|\b\d+\s+(best|top|leading|largest)\b|\blist of\b|'
                      r'\bdirectory\b|\bnear me\b|\bcompanies in\b|\bdistributors in\b.*:|\b(ranking|rankings)\b|'
                      r':\s*(list|guide|directory)\b|\bhow to\b|\bwhat is\b', re.I)
EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}', re.I)


def domain(url: str) -> str:
    host = urllib.parse.urlsplit(url if '//' in url else 'https://' + url).netloc.lower()
    return host.split('@')[-1].split(':')[0].removeprefix('www.')


def norm(text: str) -> str:
    """Lowercase, accents kept, entities decoded and whitespace collapsed: what quotes are compared on."""
    text = html_lib.unescape(text).replace('\xa0', ' ').replace('\u2019', "'").replace('\u201c', '"').replace('\u201d', '"')
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', text)).strip().lower()


def page_text(html: str) -> str:
    html = re.sub(r'(?is)<(script|style|noscript|svg|template)\b.*?</\1>', ' ', html)
    return norm(re.sub(r'(?s)<[^>]+>', ' ', html))


def paragraphs(html: str, min_words: int = 6) -> list[str]:
    """Body copy only (<p>, headings, table cells, list items with real sentences), never menus."""
    html = re.sub(r'(?is)<(script|style|noscript|nav|footer|header)\b.*?</\1>', ' ', html)
    blocks = re.findall(r'(?is)<(p|h[1-4]|td|li|blockquote)\b[^>]*>(.*?)</\1>', html)
    out = []
    for tag, b in blocks:
        t = page_text(b)
        if len(t.split()) >= (min_words if tag != 'li' else 10) and t not in out:
            out.append(t)
    return out


def decode_cfemail(html: str) -> str:
    """Appends the emails Cloudflare hides as data-cfemail, so they count as published."""
    found = []
    for hexstr in re.findall(r'data-cfemail="([0-9a-fA-F]+)"', html):
        try:
            key = int(hexstr[:2], 16)
            found.append(''.join(chr(int(hexstr[i:i + 2], 16) ^ key) for i in range(2, len(hexstr), 2)))
        except ValueError:
            continue
    return html + ' ' + ' '.join(found)


def get(url: str, timeout: int = 25, limit: int = 3_000_000) -> tuple[int | str, str, str]:
    """(status, html, final url). Non-HTML answers come back with an empty body. A site with a broken
    certificate is read once more without verification: it is a public page, nothing private is sent."""
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'en,es;q=0.8'})
    for ctx in (CTX, CTX_UNVERIFIED):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                if 'html' not in r.headers.get('Content-Type', 'text/html'):
                    return r.status, '', r.geturl()
                return r.status, r.read(limit).decode('utf-8', 'ignore'), r.geturl()
        except urllib.error.HTTPError as e:
            return e.code, '', url
        except urllib.error.URLError as e:
            if isinstance(e.reason, ssl.SSLError) and ctx is CTX:
                continue
            return type(e).__name__, '', url
        except Exception as e:  # DNS, timeout
            return type(e).__name__, '', url
    return 'SSLError', '', url


def get_json(url: str, data: bytes | None = None, headers: dict | None = None, timeout: int = 60):
    req = urllib.request.Request(url, data=data, headers={'User-Agent': UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return json.loads(r.read())


def robots_for(base: str):
    """robots.txt read with our own user agent. Missing or unreadable means allowed."""
    robots_url = urllib.parse.urljoin(base, '/robots.txt')
    req = urllib.request.Request(robots_url, headers={'User-Agent': UA})
    for ctx in (CTX, CTX_UNVERIFIED):
        try:
            with urllib.request.urlopen(req, timeout=25, context=ctx) as r:
                if r.status != 200:
                    return None
                lines = r.read(500_000).decode('utf-8', 'ignore').splitlines()
            break
        except urllib.error.URLError as e:
            if isinstance(e.reason, ssl.SSLError) and ctx is CTX:
                continue
            return None
        except Exception:
            return None
    else:
        return None
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(lines)
    return rp


# Public Overpass (OpenStreetMap) mirrors, tried in order. They are volunteer-run and go down often:
# set NOSEWORK_OVERPASS to a comma-separated list of your own (or a private) endpoint to override.
OVERPASS = [u.strip() for u in os.environ.get('NOSEWORK_OVERPASS', '').split(',') if u.strip()] or [
    'https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter',
    'https://overpass.private.coffee/api/interpreter', 'https://maps.mail.ru/osm/tools/overpass/api/interpreter']

def env_key(name: str) -> str:
    """API keys from the environment first, then from the repo's .env (never printed)."""
    if os.environ.get(name):
        return os.environ[name].strip()
    env = ROOT / '.env'
    if env.exists():
        for line in env.read_text(encoding='utf-8').splitlines():
            if line.startswith(name + '='):
                return line.split('=', 1)[1].strip().strip('"\'')
    return ''


def campaign_dir(name: str) -> Path:
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', name):
        sys.exit(f'campaign name {name!r}: use letters, digits, dots, dashes and underscores only (for example fl-miami)')
    d = DATA / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def campaigns() -> list[Path]:
    """Every campaign folder under the data directory (the imports folder and hidden folders are not campaigns)."""
    return sorted(p for p in DATA.glob('*') if p.is_dir() and p.name != 'imports' and not p.name.startswith('.'))


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding='utf-8').splitlines() if l.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    tmp = path.with_suffix('.tmp')
    tmp.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
    tmp.replace(path)


def append_jsonl(path: Path, row: dict) -> None:
    with path.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + '\n')


def log(camp: Path, msg: str) -> None:
    line = time.strftime('%Y-%m-%d %H:%M:%S ') + msg
    print(msg, flush=True)
    with (camp / 'run.log').open('a', encoding='utf-8') as fh:
        fh.write(line + '\n')


def load_sectors() -> list[dict]:
    return SECTORS_DOC['sectors']


def always_exclude() -> dict:
    return SECTORS_DOC.get('always_exclude', {})


def locale_text(mapping: dict | None, locale: str) -> str:
    """A {'en': ..., 'es': ...} value in the wanted locale, falling back to the default locale, then any."""
    mapping = mapping or {}
    return mapping.get(locale) or mapping.get(DEFAULT_LOCALE) or next(iter(mapping.values()), '')


# ---------------------------------------------------------------------------------------------------
# Who was already contacted. Local files only; nosework never talks to a server about this.
#   data/contacts.csv       the register (contacts.py builds it from campaigns; you mark what you sent)
#   data/suppress.txt       do-not-contact list, one email or domain per line (# comments allowed)
#   data/imports/*.csv      any CSV with an email and/or domain/website column (your CRM export, a bounce list)
#   data/<campaign>/exported.jsonl   everything an earlier campaign already queued
# ---------------------------------------------------------------------------------------------------
BLOCKING_STATUSES = {'queued', 'sent', 'replied', 'auto_reply', 'bounced', 'blocked'}
EMAIL_HEADERS = ('email', 'e-mail', 'email_address', 'email address', 'mail', 'to')
DOMAIN_HEADERS = ('domain', 'website', 'site', 'url', 'web')


def _add_email(domains: set, emails: set, email: str) -> None:
    email = email.strip().lower().removeprefix('mailto:')
    if '@' not in email:
        return
    emails.add(email)
    dom = email.split('@')[1].removeprefix('www.')
    if dom not in FREE_MAIL:
        domains.add(dom)


def _add_domain(domains: set, value: str) -> None:
    value = value.strip().lower()
    if not value or '@' in value or ' ' in value:
        return
    d = domain(value)
    if '.' in d:
        domains.add(d)


def read_suppress(path: Path) -> tuple[set[str], set[str]]:
    """(domains, emails) from a suppress list: one email or domain per line, # starts a comment."""
    domains, emails = set(), set()
    if path.exists():
        for line in path.read_text(encoding='utf-8', errors='ignore').splitlines():
            line = line.split('#', 1)[0].strip()
            if '@' in line:
                _add_email(domains, emails, line)
                if line.startswith('@'):  # "@example.org" blocks the whole domain
                    domains.add(line[1:].lower())
            elif line:
                _add_domain(domains, line)
    return domains, emails


def read_import(path: Path) -> tuple[set[str], set[str]]:
    """(domains, emails) from any CSV that has an email column, a domain/website column, or both."""
    domains, emails = set(), set()
    try:
        with path.open(newline='', encoding='utf-8-sig', errors='ignore') as fh:
            reader = csv.DictReader(fh)
            heads = {(h or '').strip().lower(): h for h in (reader.fieldnames or [])}
            e_cols = [heads[h] for h in EMAIL_HEADERS if h in heads]
            d_cols = [heads[h] for h in DOMAIN_HEADERS if h in heads]
            for row in reader:
                for c in e_cols:
                    for e in EMAIL_RE.findall(row.get(c) or ''):
                        _add_email(domains, emails, e)
                for c in d_cols:
                    _add_domain(domains, row.get(c) or '')
    except OSError:
        pass
    return domains, emails


def already_contacted(data_dir: Path | None = None) -> tuple[set[str], set[str]]:
    """(domains, emails) that must never get a first email: everyone in the contacts register with a
    blocking status, the suppress list, every CSV in data/imports/, and everything earlier campaigns queued.
    A free mailbox (gmail...) blocks only that address, never the whole provider."""
    base = Path(data_dir) if data_dir else DATA
    domains, emails = set(), set()
    contacts = base / 'contacts.csv'
    if contacts.exists():
        with contacts.open(newline='', encoding='utf-8') as fh:
            for r in csv.DictReader(fh):
                if (r.get('status') or '').strip() in BLOCKING_STATUSES:
                    _add_email(domains, emails, r.get('email') or '')
                    _add_domain(domains, r.get('domain') or '')
    d, e = read_suppress(base / 'suppress.txt')
    domains |= d
    emails |= e
    for f in sorted((base / 'imports').glob('*.csv')) if (base / 'imports').exists() else []:
        d, e = read_import(f)
        domains |= d
        emails |= e
    for f in base.glob('*/exported.jsonl'):
        for r in read_jsonl(f):
            _add_email(domains, emails, r.get('to') or '')
            _add_domain(domains, r.get('domain') or '')
    domains |= {x.lower() for x in PROFILE.get('company', {}).get('own_domains', [])}
    return domains, emails


def _locked(lock_path: Path):
    """Context manager: an exclusive file lock when the platform has one."""
    class _Lock:
        def __enter__(self):
            DATA.mkdir(parents=True, exist_ok=True)
            self.fh = lock_path.open('w')
            if fcntl:
                fcntl.flock(self.fh, fcntl.LOCK_EX)
            return self

        def __exit__(self, *exc):
            self.fh.close()
    return _Lock()


def next_ids(n: int) -> list[str]:
    """n new contact ids above every id used in any campaign, from id_base up. Two agents can run campaigns
    at the same time: a lock file and a shared reservation list make sure they never hand out the same id."""
    reserved_file = DATA / 'reserved_ids.json'
    with _locked(DATA / '.ids.lock'):
        used = [CONFIG['id_base'] - 1]
        pat = re.compile(r'\b' + re.escape(CONFIG['id_prefix']) + r'(\d{5,})\b')
        for p in [f for c in campaigns() for f in (c / 'ids.json',)] + [reserved_file]:
            if p.exists():
                used += [int(x) for x in pat.findall(p.read_text(encoding='utf-8', errors='ignore'))]
        start = max(used) + 1
        ids = [f"{CONFIG['id_prefix']}{start + i}" for i in range(n)]
        old = json.loads(reserved_file.read_text(encoding='utf-8')) if reserved_file.exists() else []
        reserved_file.write_text(json.dumps(old + ids), encoding='utf-8')
        return ids


def assign_variant(domain_name: str, sector: str, offer: str) -> str:
    """The A/B/C variant of a company's offer paragraph (variants.json), given once and kept forever.
    Balanced inside each sector and offer: a new company gets the variant that sector has fewest of, so a
    variant is never "all the clinics". Shared by every campaign and agent, under the same lock as the ids."""
    choices = sorted(VARIANTS['offers'].get(offer, {'A': {}}))
    path = DATA / 'assigned_variants.json'
    with _locked(DATA / '.ids.lock'):
        given = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        if domain_name in given and given[domain_name]['variant'] in choices:
            return given[domain_name]['variant']
        count = {c: 0 for c in choices}
        for g in given.values():
            if g['sector'] == sector and g['offer'] == offer and g['variant'] in count:
                count[g['variant']] += 1
        pick = min(choices, key=lambda c: (count[c], c))
        given[domain_name] = {'variant': pick, 'sector': sector, 'offer': offer, 'experiment': VARIANTS.get('experiment', '')}
        path.write_text(json.dumps(given, ensure_ascii=False, indent=0), encoding='utf-8')
        return pick


def add_profile_arg(ap) -> None:
    """Every script accepts --profile (it is read early by this module; argparse just has to know it)."""
    ap.add_argument('--profile', help='profile folder (default: profiles/example-translation-agency or $NOSEWORK_PROFILE)')
