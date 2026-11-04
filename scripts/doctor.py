"""Step 0 check: can this agent run nosework? Prints one line per check and what to do if it fails.

  python       3.10 or newer
  profile      the active profile loads (and is not still the blank template)
  data dir     the data folder can be written
  internet     the agent can open a website (without this nothing works: stop and say so)
  overpass     OpenStreetMap search (both public mirrors). Optional: without it Brave still finds companies
  brave        a Brave Search key in .env or the environment. Optional: without it only OpenStreetMap is used

Exit code 0 when nosework can run (python, profile and internet work), 1 when it can't.
Usage: python3 doctor.py [--profile <dir>]
"""
import sys
import urllib.error
import urllib.parse
import urllib.request

import common
from common import CTX, UA, env_key, get_json

OVERPASS = ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter']
TEST_URL = 'https://example.com/'


def http_status(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
            return str(r.status)
    except urllib.error.HTTPError as e:
        return str(e.code)
    except Exception as e:  # DNS, TLS, timeout, no network: all reported, none raised
        return type(e).__name__


def overpass_status(url: str) -> str:
    try:
        data = get_json(url, data=urllib.parse.urlencode({'data': '[out:json][timeout:10];node(1);out;'}).encode(), timeout=25)
        return '200' if 'elements' in data else 'unexpected answer'
    except urllib.error.HTTPError as e:
        return str(e.code)
    except Exception as e:
        return type(e).__name__


def data_writable() -> tuple[bool, str]:
    try:
        common.DATA.mkdir(parents=True, exist_ok=True)
        probe = common.DATA / '.doctor-probe'
        probe.write_text('ok', encoding='utf-8')
        probe.unlink()
        return True, str(common.DATA)
    except OSError as e:
        return False, f'{common.DATA}: {e}'


def main() -> int:
    if any(a in ('-h', '--help') for a in sys.argv[1:]):
        print(__doc__)
        return 0
    rows = []
    py_ok = sys.version_info >= (3, 10)
    rows.append(('python', py_ok, sys.version.split()[0], 'Python 3.10 or newer is needed', True))
    if common.PROFILE_ERROR:
        rows.append(('profile', False, common.PROFILE_ERROR, 'fix the profile folder or pass --profile <dir>', True))
    else:
        blank = common.profile_placeholders()
        rows.append(('profile', not blank, f'{common.PROFILE_DIR.name}' + (f' (still has {len(blank)} REPLACE_ME values)' if blank else ''),
                     'finish the onboarding in SKILL.md before drafting emails (finding companies still works)', False))
    ok, where = data_writable()
    rows.append(('data dir', ok, where, 'set NOSEWORK_DATA to a folder you can write to', True))
    web = http_status(TEST_URL)
    rows.append(('internet', web == '200', f'{TEST_URL} answers {web}',
                 'the agent has no internet: give it network access (in Codex, full-access mode). Without this, STOP', True))
    # Overpass answers its API to real queries (the same POST discover.py sends); the status page gets 406.
    ov = [overpass_status(u) for u in OVERPASS]
    rows.append(('overpass', '200' in ov, f'mirrors: {", ".join(ov)}',
                 'OpenStreetMap does not answer now: use --source brave and say so in the report (not serious)', False))
    has_key = bool(env_key('BRAVE_API_KEY'))
    rows.append(('brave', has_key, 'key found' if has_key else 'no key',
                 'no web search: only OpenStreetMap, which finds far fewer companies (copy .env.example to .env)', False))
    for name, good, what, fix, essential in rows:
        print(f"{'OK    ' if good else ('FAIL  ' if essential else 'WARN  ')}{name:9} {what}" + ('' if good else f'  ->  {fix}'))
    can_run = all(good for _, good, _, _, essential in rows if essential)
    print('\nnosework can run.' if can_run else '\nnosework CANNOT run: fix the lines marked FAIL.')
    return 0 if can_run else 1


if __name__ == '__main__':
    sys.exit(main())
