"""Step 3 (optional, OFF by default) - how old the company is, from a state's public business registry.

  FL  the Sunbiz daily filing files you saved in data/sunbiz/*c.txt (only the filings you downloaded: a match
      means "new company"). Nothing is downloaded by this script.
  TX  Texas Comptroller, franchise tax permit holders (data.texas.gov, dataset 9cir-efmm): charter date
  NY  NY Department of State, active corporations (data.ny.gov, dataset n9v6-gdp6): initial filing date
These are public open-data endpoints that change from time to time, so every lookup fails soft: an error is
recorded in the row and the run goes on. The name on a website is often not the legal name, so many companies
won't match: that is fine, the website's "since 1998" still counts. Only an exact match of the cleaned name is
accepted, never a guess. Writes <campaign>/registry.jsonl (one line per domain, resumable).
To add another registry, add a function like `socrata` and a branch in `lookup`.

Run it with `python3 prospect.py ... --registry`, or on its own:
  python3 registry.py --campaign tx-houston
"""
import argparse
import glob
import re
import time
import urllib.parse

from common import DATA, add_profile_arg, append_jsonl, campaign_dir, get_json, log, read_jsonl

SUFFIX = re.compile(r'\b(llc|l\.l\.c|inc|incorporated|corp|corporation|co|company|pa|p\.a|pllc|ltd|limited|lp|llp|pc|the)\b\.?', re.I)


def clean(name: str) -> str:
    n = re.sub(r'&amp;|&', ' and ', name.lower())
    n = SUFFIX.sub(' ', n)
    return re.sub(r'[^\w]+', ' ', n).replace('_', ' ').strip()


def sunbiz_index() -> dict[str, str]:
    idx = {}
    for f in sorted(glob.glob(str(DATA / 'sunbiz' / '*c.txt'))):
        for line in open(f, encoding='latin-1'):
            name, date = line[12:204].strip(), line[472:480].strip()
            if name and len(date) == 8:
                idx.setdefault(clean(name), f'{date[4:]}-{date[:2]}-{date[2:4]}')
    return idx


def socrata(url: str, field: str, name: str) -> list[dict]:
    first = clean(name).split()[0].upper() if clean(name) else ''
    if not first:
        return []
    where = f"upper({field}) like '{first.replace(chr(39), '')}%'"
    q = url + '?' + urllib.parse.urlencode({'$where': where, '$limit': 200})
    time.sleep(0.4)
    return get_json(q, timeout=40)


def lookup(row: dict, sb: dict) -> dict:
    name, state = row.get('name', ''), row.get('state')
    target = clean(name)
    out = {'domain': row['domain'], 'registry': '', 'registry_date': '', 'legal_name': ''}
    if not target:
        return out
    if state == 'FL':
        if target in sb:
            out.update(registry='Sunbiz (recent filings)', registry_date=sb[target], legal_name=name)
        return out
    try:
        if state == 'TX':
            for r in socrata('https://data.texas.gov/resource/9cir-efmm.json', 'taxpayer_name', name):
                if clean(r.get('taxpayer_name', '')) == target and r.get('sos_charter_date'):
                    out.update(registry='Texas Comptroller', registry_date=r['sos_charter_date'][:10], legal_name=r['taxpayer_name'])
                    break
        elif state == 'NY':
            for r in socrata('https://data.ny.gov/resource/n9v6-gdp6.json', 'current_entity_name', name):
                if clean(r.get('current_entity_name', '')) == target and r.get('initial_dos_filing_date'):
                    out.update(registry='NY Department of State', registry_date=r['initial_dos_filing_date'][:10],
                               legal_name=r['current_entity_name'])
                    break
    except Exception as e:  # soft failure: the registry is a bonus, never a requirement
        out['error'] = type(e).__name__
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description='Step 3 (optional): company age from a state business registry.')
    add_profile_arg(ap)
    ap.add_argument('--campaign', required=True)
    a = ap.parse_args()
    camp = campaign_dir(a.campaign)
    out = camp / 'registry.jsonl'
    done = {r['domain'] for r in read_jsonl(out)}
    rows = [r for r in read_jsonl(camp / 'scan.jsonl') if r.get('read_status') == 'ok' and r['domain'] not in done]
    sb = sunbiz_index() if any(r.get('state') == 'FL' for r in rows) else {}
    found = errors = 0
    for r in rows:
        res = lookup(r, sb)
        found += bool(res['registry_date'])
        errors += bool(res.get('error'))
        append_jsonl(out, res)
    log(camp, f'registry: {len(rows)} looked up, {found} found in the state registry'
              + (f', {errors} lookups failed (ignored)' if errors else ''))


if __name__ == '__main__':
    main()
