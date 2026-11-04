import unittest

import helpers  # noqa: F401
import scan
import score

LADDER = {
    'partner_offers': ['referrals'],
    'rules': [
        {'offer': 'localization', 'when': {'sectors': ['health'], 'missing_alt_version': True}, 'reason': 'public-facing'},
        {'offer': 'sector', 'when': {'signals_any': ['B', 'D']}, 'reason': 'document work'},
        {'offer': 'localization', 'when': {'signals_all': ['E']}, 'reason': 'serves the audience, no alt version'},
        {'offer': 'new_website', 'when': {'site_dated': True, 'missing_alt_version': True, 'signals_none': ['H', 'E']}, 'reason': 'dated'},
    ],
    'alternates': {'localization': {'active': True}, 'new_website': {'active': False}},
}


def row(signals=(), alt=False, dated=False):
    return {'signals': [{'id': s} for s in signals], 'has_alt_version': alt, 'site_health': {'dated': dated}}


class OfferLadder(unittest.TestCase):
    def test_partner_sector_always_gets_its_own_offer(self):
        self.assertEqual(score.choose_offer(row(['E']), {'id': 'accounting', 'offer': 'referrals'}, LADDER)[0], 'referrals')

    def test_public_facing_sector_without_alt_version_gets_localization(self):
        self.assertEqual(score.choose_offer(row(['B']), {'id': 'health', 'offer': 'sample'}, LADDER)[0], 'localization')

    def test_public_facing_sector_with_alt_version_falls_through(self):
        self.assertEqual(score.choose_offer(row(['B'], alt=True), {'id': 'health', 'offer': 'sample'}, LADDER)[0], 'sample')

    def test_document_signals_pick_the_sector_offer(self):
        offer, why = score.choose_offer(row(['D']), {'id': 'food', 'offer': 'sample'}, LADDER)
        self.assertEqual(offer, 'sample')
        self.assertIn('D', why)

    def test_audience_signal_without_alt_version_gets_localization(self):
        self.assertEqual(score.choose_offer(row(['H', 'E']), {'id': 'food', 'offer': 'sample'}, LADDER)[0], 'localization')

    def test_inactive_alternate_is_skipped_and_fallback_is_sector_offer(self):
        self.assertEqual(score.choose_offer(row(dated=True), {'id': 'food', 'offer': 'sample'}, LADDER)[0], 'sample')

    def test_empty_ladder_gives_sector_offer(self):
        self.assertEqual(score.choose_offer(row(['H']), {'id': 'food', 'offer': 'sample'}, {})[0], 'sample')


class Points(unittest.TestCase):
    def test_points_add_up(self):
        r = {'signals': [{'id': 'H', 'points': 2}, {'id': 'I', 'points': 2}]}
        sector = {'priority': 1}
        # signals 4 + priority 1 (+2) + small (+2) + new company (+1) + named contact (+1)
        pts = score.points_for(r, sector, {'band': 'small'}, {'since': score.YEAR - 1}, {'name': 'Ann Lee'})
        self.assertEqual(pts, 10)

    def test_minimum_inputs(self):
        self.assertEqual(score.points_for({'signals': []}, {'priority': 3}, {'band': 'unknown'}, {'since': None}, None), 0)

    def test_age_prefers_registry_then_site_then_copyright(self):
        self.assertEqual(score.age_of({'age': {'founded': 1998}}, {'registry_date': '2024-05-01', 'registry': 'R'})['since'], 2024)
        self.assertEqual(score.age_of({'age': {'founded': 1998}}, {})['since'], 1998)
        self.assertEqual(score.age_of({'age': {'oldest_copyright': 2009}}, {})['since'], 2009)
        self.assertIsNone(score.age_of({'age': {}}, {})['since'])


class Contacts(unittest.TestCase):
    def test_decision_maker_with_own_email_wins(self):
        r = {'emails': [{'email': 'info@acme-bakery.example.com', 'page': 'p', 'wrong_inbox': False},
                        {'email': 'ann@acme-bakery.example.com', 'page': 'p', 'wrong_inbox': False}],
             'people': [{'name': 'Ann Lee', 'role': 'Owner', 'email': 'ann@acme-bakery.example.com', 'decides': True}]}
        email, person = score.choose_contact(r)
        self.assertEqual(email['email'], 'ann@acme-bakery.example.com')
        self.assertEqual(person['name'], 'Ann Lee')

    def test_general_inbox_beats_nothing_and_wrong_inboxes_never_count(self):
        r = {'emails': [{'email': 'jobs@acme-bakery.example.com', 'page': 'p', 'wrong_inbox': True},
                        {'email': 'info@acme-bakery.example.com', 'page': 'p', 'wrong_inbox': False}], 'people': []}
        self.assertEqual(score.choose_contact(r)[0]['email'], 'info@acme-bakery.example.com')
        self.assertEqual(score.choose_contact({'emails': [{'email': 'jobs@x.example.com', 'page': 'p', 'wrong_inbox': True}], 'people': []}), (None, None))

    def test_disposable_address_is_never_chosen(self):
        r = {'emails': [{'email': 'a@0-mail.com', 'page': 'p', 'wrong_inbox': False}], 'people': []}
        self.assertEqual(score.choose_contact(r), (None, None))


PAGE_HOME = ('<html lang="en"><body><p>We serve the Hispanic community with bilingual staff at every location in town.</p>'
             '<p>Our plant is certified and we export pastries to Puerto Rico every week.</p></body></html>')
PAGE_JOBS = '<html><body><p>Now hiring front counter staff, bilingual English and Spanish required for this position.</p></body></html>'
PAGE_PDF = '<html><body><a href="/docs/menu.pdf">menu</a> <a href="/docs/menu_es.pdf">menu</a></body></html>'
PAGES = [('home', 'https://x.example.com/', PAGE_HOME), ('jobs', 'https://x.example.com/jobs', PAGE_JOBS),
         ('documents', 'https://x.example.com/docs', PAGE_PDF)]


class SignalDetection(unittest.TestCase):
    def test_example_profile_signals_with_quotes(self):
        ids = {s['id']: s for s in scan.detect_signals('food', PAGES, has_alt=False)}
        self.assertTrue({'H', 'E', 'B', 'I', 'D'} <= set(ids), ids.keys())
        self.assertIn('hispanic community', ids['H']['quote'])
        self.assertEqual(ids['B']['page'], 'https://x.example.com/jobs')
        self.assertEqual(ids['D']['example'].endswith('menu.pdf'), True)  # the _es PDF is excluded

    def test_alt_version_present_removes_E(self):
        ids = {s['id'] for s in scan.detect_signals('food', PAGES, has_alt=True)}
        self.assertIn('H', ids)
        self.assertNotIn('E', ids)

    def test_custom_signal_definitions_from_data(self):
        defs = [{'id': 'X', 'label': 'hires bookkeepers', 'points': 3, 'page_types': ['jobs'], 'terms': ['front counter']},
                {'id': 'Y', 'label': 'pattern', 'points': 1, 'patterns': [r'export\w* pastries']},
                {'id': 'Z', 'label': 'needs X and Y', 'points': 2, 'requires': ['X', 'Y']}]
        out = scan.detect_signals('food', PAGES, False, defs)
        self.assertEqual([s['id'] for s in out], ['X', 'Y', 'Z'])
        self.assertEqual(sum(s['points'] for s in out), 6)

    def test_empty_signal_list_is_valid(self):
        self.assertEqual(scan.detect_signals('food', PAGES, False, []), [])

    def test_size_bands(self):
        self.assertEqual([scan.size_band(n) for n in (None, 4, 12, 80, 400)], ['unknown', 'micro', 'small', 'medium', 'large'])


if __name__ == '__main__':
    unittest.main()
