"""scan.scan() against a throwaway local web server: pages, robots.txt, people, forms, signals."""
import functools
import http.server
import tempfile
import threading
import unittest
from pathlib import Path

import helpers  # noqa: F401
import scan

INDEX = ('<html lang="en"><head><title>Sunrise Bakery | Springfield</title><meta property="og:site_name" content="Sunrise Bakery"></head>'
         '<body><h1>Sunrise Bakery</h1><p>We bake guava pastelitos and cuban bread every morning for cafeterias across Springfield and '
         'export frozen empanadas to Puerto Rico.</p><p>Founded in 2012, our team of 14 serves the Hispanic community with bilingual '
         'staff at our Springfield shop. Springfield, FL 33025.</p><a href="/about.html">About</a> <a href="/contact.html">Contact</a> '
         '<a href="/jobs.html">Careers</a></body></html>')
PAGES = {
    'index.html': INDEX,
    'about.html': '<html><body><h2>Our team</h2><div>Maria Gomez</div><div>Owner</div><p>Sunrise Bakery is a family bakery serving '
                  'restaurants and cafeterias around Springfield with fresh bread every day.</p></body></html>',
    'contact.html': '<html><body><p>Write to sunrisebakery.owner@gmail.com or use the form.</p><form action="/send" method="post">'
                    '<input name="your-name"><input name="your-email"><textarea name="your-message"></textarea></form></body></html>',
    'jobs.html': '<html><body><p>We are hiring counter staff. Bilingual English and Spanish is required for this position at our shop.</p></body></html>',
}


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve(files: dict[str, str]):
    root = Path(tempfile.mkdtemp())
    for name, body in files.items():
        (root / name).write_text(body, encoding='utf-8')
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(root)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f'http://127.0.0.1:{server.server_address[1]}/'


CAND = {'name': 'Sunrise Bakery', 'sector': 'food', 'county': 'Springfield County', 'state': 'FL', 'city': 'Springfield',
        'source': 'osm', 'osm_email': ''}


class ScanLocalSite(unittest.TestCase):
    def setUp(self):
        scan.PAUSE = 0
        self.evid = Path(tempfile.mkdtemp())

    @staticmethod
    def stop(server):
        server.shutdown()
        server.server_close()

    def test_extracts_what_the_site_publishes(self):
        server, url = serve(PAGES)
        self.addCleanup(self.stop, server)
        r = scan.scan({**CAND, 'site': url}, self.evid)
        self.assertEqual(r['read_status'], 'ok')
        self.assertEqual([e['email'] for e in r['emails']], ['sunrisebakery.owner@gmail.com'])
        self.assertEqual((r['people'][0]['name'], r['people'][0]['role'], r['people'][0]['decides']), ('Maria Gomez', 'Owner', True))
        self.assertEqual(r['forms'][0]['provider'], 'html')
        self.assertEqual(r['forms'][0]['fields'], ['your-name', 'your-email', 'your-message'])
        ids = {s['id']: s for s in r['signals']}
        self.assertTrue({'H', 'E', 'B', 'I', 'S'} <= set(ids))
        self.assertIn('/jobs.html', ids['B']['page'])
        self.assertEqual((r['size']['employees'], r['size']['band'], r['age']['founded']), (14, 'small', 2012))
        self.assertTrue(r['in_region'] and r['name_on_site'] and not r['has_alt_version'])
        self.assertEqual(len(list((self.evid / '127.0.0.1').glob('*.html'))), 4)  # the pages are kept as evidence

    def test_robots_txt_is_respected(self):
        server, url = serve({**PAGES, 'robots.txt': 'User-agent: *\nDisallow: /\n'})
        self.addCleanup(self.stop, server)
        r = scan.scan({**CAND, 'site': url}, self.evid)
        self.assertIn('robots.txt', r['read_status'])
        self.assertNotIn('emails', r)

    def test_profile_exclusion_patterns_skip_competitors(self):
        html = INDEX.replace('Sunrise Bakery | Springfield', 'Best Translation Services')
        server, url = serve({'index.html': html})
        self.addCleanup(self.stop, server)
        r = scan.scan({**CAND, 'site': url}, self.evid)
        self.assertIn('excluded', r['read_status'])


if __name__ == '__main__':
    unittest.main()
