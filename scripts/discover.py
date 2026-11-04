"""Step 1 - candidates: businesses that exist and have their own website.

Two free sources, both public:
  osm    OpenStreetMap through the Overpass API, county by county and sector by sector (ODbL data).
  brave  Brave Search API ("food manufacturer Hialeah FL"), only when BRAVE_API_KEY is set. Directories
         and platforms (Yelp, Facebook, Sunbiz...) are dropped: only the business's own site counts.
Chains (any OSM brand tag), government and whatever the profile excludes (sectors.json -> always_exclude,
profile.json -> exclude_site_patterns) never enter.
Writes <campaign>/candidates.jsonl, adding to what is there (resumable, no duplicates by domain).

Usage:
  python3 discover.py --campaign fl-miami --state FL --counties "Miami-Dade County" [--sectors food,health]
                      [--source osm|brave|both] [--max-per-sector 400]
"""
import argparse
import json
import re
import time
import urllib.parse

from common import (DIRECTORIES, EXCLUDED_SITE, LISTICLE, ROOT, add_profile_arg, always_exclude, append_jsonl,
                    campaign_dir, campaigns, domain, env_key, get_json, load_sectors, log, read_jsonl)

OVERPASS = ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter']
REGIONS = json.loads((ROOT / 'references' / 'regions.json').read_text(encoding='utf-8'))['states']
EXCLUDE = always_exclude()
EXCLUDE_NAME = re.compile(EXCLUDE['name_regex'], re.I) if EXCLUDE.get('name_regex') else re.compile(r'(?!x)x')


def excluded_tags(tags: dict) -> bool:
    if any(k.startswith('brand') for k in tags) or tags.get('operator:type') in ('public', 'government'):
        return True
    return any(re.search(v, tags.get(k, '')) for k, v in EXCLUDE.get('osm', []))


def overpass_sector(county: str, iso: str, sector: dict, admin_level: str = '6') -> list[dict]:
    """One query per sector and county (one big query times out on large counties). A timeout is
    retried on the mirror and reported, never taken as "no businesses"."""
    parts = ''.join(f'nwr["{k}"~"{v}"]["{w}"](area.c);' for k, v in sector['osm'] for w in ('website', 'contact:website'))
    q = (f'[out:json][timeout:180];area["ISO3166-2"="{iso}"]->.s;rel(area.s)["name"="{county}"]["admin_level"="{admin_level}"];'
         f'map_to_area->.c;({parts});out tags;')
    for attempt, url in enumerate(OVERPASS * 2):
        try:
            data = get_json(url, data=urllib.parse.urlencode({'data': q}).encode(), timeout=240)
            if data.get('elements') or 'remark' not in data:
                return data.get('elements', [])
            reason = data.get('remark', '')[:80]
        except Exception as e:
            reason = type(e).__name__
        print(f'   overpass {county} {sector["id"]}: {reason}, retry {attempt + 1}', flush=True)
        time.sleep(20 * (attempt + 1))
    raise RuntimeError(f'Overpass did not answer for {county} / {sector["id"]}')


def from_osm(county: str, state: str, sector: dict) -> list[dict]:
    rows = []
    region = REGIONS[state]
    for e in overpass_sector(county, region['iso'], sector, region.get('admin_level', '6')):
        t = e.get('tags', {})
        site = (t.get('website') or t.get('contact:website') or '').strip().split(';')[0]
        name = t.get('name', '').strip()
        if not site or not name or excluded_tags(t) or EXCLUDE_NAME.search(name):
            continue
        rows.append({'name': name, 'site': site if site.startswith('http') else 'https://' + site, 'sector': sector['id'],
                     'county': county, 'state': state, 'city': t.get('addr:city', ''),
                     'address': ' '.join(x for x in (t.get('addr:housenumber', ''), t.get('addr:street', '')) if x),
                     'phone': t.get('phone') or t.get('contact:phone', ''),
                     'osm_email': t.get('email') or t.get('contact:email', ''),
                     'osm_start': t.get('start_date', ''), 'source': 'osm'})
    return rows


def from_brave(county: str, state: str, sector: dict, cities: list[str]) -> list[dict]:
    key = env_key('BRAVE_API_KEY')
    if not key:
        return []
    rows = []
    for city in cities:
        for term in sector.get('searches', []):
            q = f'{term} {city} {state}'
            url = 'https://api.search.brave.com/res/v1/web/search?count=20&q=' + urllib.parse.quote(q)
            time.sleep(1.1)  # free plan: 1 query a second
            try:
                res = get_json(url, headers={'Accept': 'application/json', 'X-Subscription-Token': key}, timeout=30)
            except Exception as e:
                print(f'   brave "{q}": {type(e).__name__}', flush=True)
                continue
            for r in res.get('web', {}).get('results', []):
                link, title = r.get('url', ''), r.get('title', '')
                if not link or DIRECTORIES.search(domain(link)) or EXCLUDE_NAME.search(title) or LISTICLE.search(title):
                    continue
                # The home page, not the article or listing the search landed on.
                parts = urllib.parse.urlsplit(link)
                rows.append({'name': re.split(r'\s[|\-\u2013\u00b7]\s', title)[0].strip()[:90], 'site': f'{parts.scheme}://{parts.netloc}/',
                             'sector': sector['id'], 'county': county, 'state': state, 'city': city, 'address': '',
                             'phone': '', 'osm_email': '', 'osm_start': '', 'source': f'brave: {q}'})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description='Step 1: find businesses with their own website (OpenStreetMap, Brave).')
    add_profile_arg(ap)
    ap.add_argument('--campaign', required=True)
    ap.add_argument('--state', required=True, choices=sorted(REGIONS))
    ap.add_argument('--counties', help='comma separated; default: every county of the state in regions.json')
    ap.add_argument('--sectors', help='comma separated sector ids; default: every active sector')
    ap.add_argument('--source', default='both', choices=['osm', 'brave', 'both'])
    ap.add_argument('--max-per-sector', type=int, default=400, help='per county')
    a = ap.parse_args()
    camp = campaign_dir(a.campaign)
    out = camp / 'candidates.jsonl'
    seen = {domain(r['site']) for r in read_jsonl(out)}
    # A company another campaign already found is never read twice either.
    seen |= {domain(r['site']) for c in campaigns() if c != camp for r in read_jsonl(c / 'candidates.jsonl')}
    wanted = a.sectors.split(',') if a.sectors else None
    sectors = [s for s in load_sectors() if s.get('active', True) and (not wanted or s['id'] in wanted)]
    region = {c['county']: c['cities'] for c in REGIONS[a.state]['counties']}
    counties = [c.strip() for c in a.counties.split(',')] if a.counties else list(region)
    done_file = camp / 'sources_done.json'
    done = json.loads(done_file.read_text(encoding='utf-8')) if done_file.exists() else []
    # Searches done in any other campaign count too: a county and sector are never searched twice.
    elsewhere = {k for c in campaigns() if c != camp and (c / 'sources_done.json').exists()
                 for k in json.loads((c / 'sources_done.json').read_text(encoding='utf-8'))}
    for county in counties:
        for s in sectors:
            for src in (['osm', 'brave'] if a.source == 'both' else [a.source]):
                key = f'{src}|{a.state}|{county}|{s["id"]}'
                if key in done:
                    continue
                if key in elsewhere:
                    log(camp, f'{src} {county} - {s["id"]}: already searched in another campaign, not repeating')
                    continue
                try:
                    rows = from_osm(county, a.state, s) if src == 'osm' else from_brave(county, a.state, s, region.get(county, []))
                except RuntimeError as e:
                    log(camp, f'FAILED {e}; it will be retried on the next run')
                    continue
                kept = 0
                for r in rows:
                    d = domain(r['site'])
                    if not d or d in seen or EXCLUDED_SITE.search(d) or DIRECTORIES.search(d) or kept >= a.max_per_sector:
                        continue
                    seen.add(d)
                    append_jsonl(out, r)
                    kept += 1
                log(camp, f'{src} {county} - {s["id"]}: {len(rows)} found, {kept} new')
                done.append(key)
                done_file.write_text(json.dumps(done, indent=0), encoding='utf-8')
                if src == 'osm':
                    time.sleep(3)  # respect for the public Overpass servers
    # Only this campaign's companies: `seen` also holds other campaigns' domains, kept out on purpose.
    log(camp, f'candidates in this campaign: {len(read_jsonl(out))} -> {out}')


if __name__ == '__main__':
    main()
