"""Offline end-to-end test: score -> draft -> verify -> export on a hand-made scan result, in a temp data dir."""
import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import helpers
from helpers import SCRIPTS

DOMAIN = 'sunrise-bakery.example.org'
HTML = ('<html lang="en"><body><h1>Sunrise Bakery</h1><p>We bake guava pastelitos and cuban bread every morning for '
        'cafeterias across Springfield and export frozen empanadas to Puerto Rico.</p>'
        '<p>Email info@sunrise-bakery.example.org</p></body></html>')
PROOF = 'bake guava pastelitos and cuban bread every morning'
LINE = ('Guava pastelitos for local cafeterias and frozen empanadas heading to Puerto Rico suggest your orders '
        'already cross into Spanish speaking markets.')


def scan_row(domain: str = DOMAIN) -> dict:
    return {'name': 'Sunrise Bakery LLC', 'site': f'https://{domain}/', 'sector': 'food', 'county': 'Example County', 'state': 'FL',
            'city': 'Springfield', 'address': '', 'phone': '', 'osm_email': '', 'osm_start': '', 'source': 'osm', 'domain': domain,
            'read_status': 'ok', 'read_date': '2026-01-01', 'title': 'Sunrise Bakery', 'name_on_site': True, 'name_reliable': True,
            'in_region': True, 'pages': [{'type': 'home', 'url': f'https://{domain}/'}],
            'emails': [{'email': f'info@{domain}', 'page': f'https://{domain}/', 'wrong_inbox': False}],
            'people': [], 'forms': [], 'phones': [], 'site_locale': 'en', 'has_alt_version': False,
            'signals': [{'id': 'I', 'label': 'works with other countries', 'points': 2, 'page': f'https://{domain}/', 'quote': 'export frozen empanadas to puerto rico'},
                        {'id': 'D', 'label': 'English-only PDFs', 'points': 2, 'detail': '2 linked PDF documents'}],
            'size': {'employees': 20, 'locations': 1, 'people_on_site': 0, 'quote': '', 'band': 'small'},
            'age': {'founded': 2010, 'how': 'since 2010', 'oldest_copyright': 2010}, 'site_health': {'signs': [], 'count': 0, 'dated': False},
            'summary': {'home': 'We bake guava pastelitos and cuban bread every morning.', 'about': '', 'services': ['Pastelitos']}}


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp())
        self.env = {**os.environ, 'NOSEWORK_DATA': str(self.data), 'NOSEWORK_SKIP_DNS': '1'}

    def run_step(self, script: str, campaign: str, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPTS / f'{script}.py'), '--campaign', campaign, *extra], env=self.env,
                              capture_output=True, text=True, timeout=120)

    def make_campaign(self, name: str, domain: str = DOMAIN) -> Path:
        camp = self.data / name
        (camp / 'evidence' / domain).mkdir(parents=True)
        (camp / 'evidence' / domain / '0_home.html').write_text(HTML, encoding='utf-8')
        (camp / 'scan.jsonl').write_text(json.dumps(scan_row(domain)) + '\n', encoding='utf-8')
        return camp

    def test_full_offline_flow_and_never_repeat(self):
        camp = self.make_campaign('demo')
        r = self.run_step('score', 'demo')
        self.assertEqual(r.returncode, 0, r.stderr)
        lead = json.loads((camp / 'leads.jsonl').read_text().splitlines()[0])
        self.assertEqual(lead['status'], 'to_draft')
        self.assertTrue(lead['id'].startswith('L1'))
        self.assertEqual(lead['offer'], 'sample')

        r = self.run_step('draft', 'demo')  # pauses: the agent has not written the first line yet
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(lead['id'], (camp / 'FOR_DRAFTING.md').read_text())

        (camp / 'manual_lines.jsonl').write_text(json.dumps({'id': lead['id'], 'first_line': 'Great site!', 'proof': 'nothing'}) + '\n')
        self.assertEqual(self.run_step('draft', 'demo').returncode, 2)  # a bad line is rejected, not accepted
        self.assertTrue((camp / 'line_rejections.jsonl').exists())

        (camp / 'manual_lines.jsonl').write_text(json.dumps({'id': lead['id'], 'first_line': LINE, 'proof': PROOF}) + '\n')
        r = self.run_step('draft', 'demo')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        draft = json.loads((camp / 'drafts.jsonl').read_text().splitlines()[0])
        self.assertIn(LINE, draft['body'])
        self.assertIn('Hello Sunrise Bakery team,', draft['body'])
        self.assertIn('Alex Example', draft['body'])
        self.assertIn('just reply "no"', draft['body'])

        r = self.run_step('verify', 'demo', '--offline')
        self.assertEqual(r.returncode, 1)  # offline can never be a final OK
        self.assertEqual(len((camp / 'verified.jsonl').read_text().splitlines()), 1)
        self.assertIn('RESULT: FAIL (the live check is missing)', (camp / 'VERIFICATION.md').read_text())

        r = self.run_step('export', 'demo')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        queue = json.loads((camp / 'queue-demo.json').read_text())
        self.assertEqual([q['to'] for q in queue], [f'info@{DOMAIN}'])
        self.assertTrue((camp / 'BATCHES_demo.md').exists() and (camp / 'SUMMARY.md').exists())
        with (self.data / 'contacts.csv').open(newline='', encoding='utf-8') as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual([(r['email'], r['status']) for r in rows], [(f'info@{DOMAIN}', 'queued')])

        # the same company found again by another campaign is never prepared twice
        camp2 = self.make_campaign('demo2')
        self.assertEqual(self.run_step('score', 'demo2').returncode, 0)
        lead2 = json.loads((camp2 / 'leads.jsonl').read_text().splitlines()[0])
        self.assertEqual((lead2['status'], lead2['channel']), ('discarded', 'already_contacted'))

    def test_suppress_list_and_import_stop_a_company_before_drafting(self):
        (self.data / 'suppress.txt').write_text(f'{DOMAIN}\n', encoding='utf-8')
        camp = self.make_campaign('demo')
        self.assertEqual(self.run_step('score', 'demo').returncode, 0)
        lead = json.loads((camp / 'leads.jsonl').read_text().splitlines()[0])
        self.assertEqual(lead['channel'], 'already_contacted')

    def test_template_profile_refuses_to_draft(self):
        camp = self.make_campaign('demo')
        r = self.run_step('draft', 'demo', '--profile', 'profiles/_template')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('REPLACE_ME', r.stdout + r.stderr)

    def test_coverage_and_status_run_on_a_campaign(self):
        self.make_campaign('demo')
        self.assertEqual(self.run_step('score', 'demo').returncode, 0)
        r = subprocess.run([sys.executable, str(SCRIPTS / 'coverage.py')], env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.data / 'READ_FIRST.md').exists())
        r = subprocess.run([sys.executable, str(SCRIPTS / 'status.py')], env=self.env, capture_output=True, text=True, timeout=60)
        self.assertIn('demo:', r.stdout)


if __name__ == '__main__':
    unittest.main()
