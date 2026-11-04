import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401
import draft
import quality
from common import norm, page_text

SITE_HTML = ('<html><body><p>We bake guava pastelitos and cuban bread every morning for cafeterias across Springfield '
             'and export frozen empanadas to Puerto Rico.</p></body></html>')
SITE_TEXT = page_text(SITE_HTML)
PROOF = 'bake guava pastelitos and cuban bread every morning'
GOOD = ('Guava pastelitos for local cafeterias and frozen empanadas heading to Puerto Rico suggest your orders '
        'already cross into Spanish speaking markets.')


class QuotedProof(unittest.TestCase):
    def test_good_line_passes(self):
        self.assertEqual(draft.line_problems(GOOD, PROOF, 'en', SITE_TEXT), [])

    def test_proof_must_appear_letter_by_letter(self):
        probs = draft.line_problems(GOOD, 'bake sourdough rolls and cuban bread daily', 'en', SITE_TEXT)
        self.assertTrue(any('does not appear' in p for p in probs))

    def test_proof_is_compared_normalised(self):
        probs = draft.line_problems(GOOD, 'BAKE  guava pastelitos\nand cuban bread every morning', 'en', SITE_TEXT)
        self.assertEqual(probs, [])

    def test_missing_or_short_proof(self):
        self.assertTrue(any('missing' in p for p in draft.line_problems(GOOD, '', 'en', SITE_TEXT)))
        self.assertTrue(any('missing' in p for p in draft.line_problems(GOOD, 'guava pastelitos', 'en', SITE_TEXT)))

    def test_copying_five_words_in_a_row_is_rejected(self):
        line = 'Every day you bake guava pastelitos and cuban bread before dawn, so your orders reach Spanish speaking cafes.'
        self.assertTrue(any('5 words' in p for p in draft.line_problems(line, PROOF, 'en', SITE_TEXT)))


class LineRules(unittest.TestCase):
    def test_length_bounds(self):
        self.assertTrue(any('words' in p for p in draft.line_problems('Too short for a line.', PROOF, 'en', SITE_TEXT)))

    def test_greeting_is_rejected(self):
        self.assertTrue(any('greeting' in p for p in draft.line_problems('Hello team, ' + GOOD, PROOF, 'en', SITE_TEXT)))

    def test_promises_are_rejected(self):
        for bad in ('fast', 'best', 'quality', '20%', '$9', 'same-day', 'guarantee'):
            line = GOOD.replace('suggest', f'suggest {bad}')
            self.assertTrue(any('price' in p for p in draft.line_problems(line, PROOF, 'en', SITE_TEXT)), bad)

    def test_wrong_language_is_rejected(self):
        self.assertTrue(any('language' in p for p in draft.line_problems(GOOD, PROOF, 'es', SITE_TEXT)))


class BannedPhrases(unittest.TestCase):
    def test_universal_ban_flattery_and_cliches(self):
        for bad in ('impressive', 'I came across your site', 'outdated', 'lawsuit'):
            self.assertTrue(draft.banned_hits(norm(f'It is {bad} really')), bad)

    def test_punctuation_bans(self):
        self.assertTrue(draft.banned_hits('one; two'))
        self.assertTrue(draft.banned_hits('one \u2014 two'))

    def test_profile_phrase_ban(self):
        self.assertIn('human translation', draft.banned_hits('we do human translation'))

    def test_single_word_bans_need_whole_words(self):
        self.assertFalse(draft.banned_hits('a fearless approach'))  # 'fea' is not inside a whole word
        self.assertTrue(draft.banned_hits('what an ugly site'))

    def test_clean_text_has_no_hits(self):
        self.assertEqual(draft.banned_hits(norm(GOOD)), [])


class QualityRules(unittest.TestCase):
    def _vocab(self, sites: dict[str, str]):
        tmp = Path(tempfile.mkdtemp())
        for dom, html in sites.items():
            d = tmp / 'evidence' / dom
            d.mkdir(parents=True)
            (d / '0_home.html').write_text(html, encoding='utf-8')
        return quality.Vocabulary(tmp)

    def test_generic_line_is_rejected_and_specific_passes(self):
        vocab = self._vocab({'a.example.com': SITE_HTML, 'b.example.com': '<p>We repair roofs and gutters for homeowners everywhere.</p>'})
        generic = 'Your company provides services for clients across the area and works with many people.'
        self.assertTrue(any('generic' in p for p in quality.problems(generic, PROOF, 'Acme', [], vocab, 'a.example.com')))
        self.assertEqual(quality.problems(GOOD, PROOF, 'Acme', [], vocab, 'a.example.com'), [])

    def test_repeated_ending_after_two_uses(self):
        ending = ', and many kitchens here work in Spanish every day'
        others = [f'Line about thing number {i} on their site{ending}' for i in range(2)]
        probs = quality.problems('A third distinct line about guava pastelitos' + ending, PROOF, 'Acme', others)
        self.assertTrue(any('ending' in p for p in probs))

    def test_vague_reason_from_profile_is_rejected_unless_a_market_is_named(self):
        line = 'Your guava pastelitos and empanadas sell in a city where Spanish is widely spoken among shoppers.'
        self.assertTrue(any('filler' in p for p in quality.problems(line, PROOF, 'Acme', [])))
        ok = 'Your frozen empanadas ship to Puerto Rico, where Spanish is widely spoken among shoppers and retailers.'
        self.assertFalse(any('filler' in p for p in quality.problems(ok, PROOF, 'Acme', [])))

    def test_claim_about_their_clients_is_rejected(self):
        line = 'Your cafeteria clients read Spanish and order guava pastelitos with empanadas every single week.'
        self.assertTrue(any('claims' in p for p in quality.problems(line, PROOF, 'Acme', [])))

    def test_template_frame_repeated_is_rejected(self):
        frame = 'Your practice highlights {a} along with {b} in town, and patients search for {c} in Spanish near here'
        others = [frame.format(a=f'alpha{i}', b=f'beta{i}', c=f'gamma{i}') for i in range(6)]
        self.assertGreaterEqual(quality.template_hits(frame.format(a='kiwi', b='lemon', c='pear'), others), 2)


if __name__ == '__main__':
    unittest.main()
