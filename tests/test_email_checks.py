import unittest

import helpers  # noqa: F401  (sets up sys.path)
import mail
import scan
from common import PLACEHOLDER_EMAIL, WRONG_INBOX, decode_cfemail, domain, norm


class EmailExtraction(unittest.TestCase):
    def test_finds_own_domain_and_free_mail_only(self):
        html = '<a href="mailto:Sales@Acme-Bakery.example.com">x</a> bob@gmail.com other@elsewhere.org'
        self.assertEqual(scan.emails_on('acme-bakery.example.com', html), ['sales@acme-bakery.example.com', 'bob@gmail.com'])

    def test_ignores_placeholders_and_image_names(self):
        html = 'your@email.com user@example.com logo@2x.png info@sentry.io name@domain.com'
        self.assertEqual(scan.emails_on('example.com', html), [])

    def test_strips_phone_number_glued_before_address(self):
        found = scan.emails_on('shop.example.com', 'Call 555-123-4567info@shop.example.com')
        self.assertEqual(found, ['info@shop.example.com'])

    def test_obfuscated_at_sign_variants(self):
        self.assertEqual(scan.emails_on('shop.example.com', 'ann&#64;shop.example.com'), ['ann@shop.example.com'])
        self.assertEqual(scan.emails_on('shop.example.com', 'ann [at] shop.example.com'), ['ann@shop.example.com'])

    def test_decodes_cloudflare_protected_email(self):
        key = 0x42
        plain = 'ann@shop.example.com'
        encoded = f'{key:02x}' + ''.join(f'{ord(c) ^ key:02x}' for c in plain)
        html = f'<a class="__cf_email__" data-cfemail="{encoded}">[email protected]</a>'
        self.assertIn(plain, decode_cfemail(html))
        self.assertEqual(scan.emails_on('shop.example.com', html), [plain])

    def test_longer_address_with_junk_prefix_loses_to_clean_one(self):
        out = scan.emails_on('shop.example.com', 'xxinfo@shop.example.com info@shop.example.com')
        self.assertEqual(out, ['info@shop.example.com'])


class InboxChecks(unittest.TestCase):
    def test_wrong_inboxes(self):
        for local in ('hr', 'jobs', 'careers', 'noreply', 'privacy', 'billing', 'webmaster'):
            self.assertTrue(WRONG_INBOX.match(local), local)
        for local in ('info', 'maria', 'sales', 'owner'):
            self.assertFalse(WRONG_INBOX.match(local), local)

    def test_placeholder_pattern(self):
        self.assertTrue(PLACEHOLDER_EMAIL.search('name@domain.com'))
        self.assertFalse(PLACEHOLDER_EMAIL.search('maria@acme-bakery.example.com'))


class DisposableAndRole(unittest.TestCase):
    def test_disposable_domain(self):
        self.assertTrue(mail.is_disposable('anyone@0-mail.com'))
        self.assertFalse(mail.is_disposable('anyone@example.com'))

    def test_role_mailbox(self):
        self.assertTrue(mail.is_role('info@example.com'))
        self.assertTrue(mail.is_role('sales@example.com'))
        self.assertFalse(mail.is_role('maria.lopez@example.com'))

    def test_role_mailbox_with_trailing_digits(self):
        self.assertTrue(mail.is_role('info2@example.com'))

    def test_dns_skip_is_unknown_not_failure(self):
        ok, _ = mail.mail_domain('some-company.example')
        self.assertIsNone(ok)  # NOSEWORK_SKIP_DNS=1 in tests: unknown, never False
        self.assertEqual(mail.mail_domain('gmail.com'), (True, ''))


class TextHelpers(unittest.TestCase):
    def test_domain(self):
        self.assertEqual(domain('https://www.Example.com/path?x=1'), 'example.com')
        self.assertEqual(domain('example.org'), 'example.org')

    def test_norm_collapses_and_lowercases(self):
        self.assertEqual(norm('  We\u00a0BAKE &amp;   sell\n\u201cbread\u201d '), 'we bake & sell "bread"')


if __name__ == '__main__':
    unittest.main()
