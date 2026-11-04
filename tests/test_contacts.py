import csv
import json
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401
import common
import contacts


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    with path.open('w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


class AlreadyContacted(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_empty_data_dir_blocks_only_own_domains(self):
        domains, emails = common.already_contacted(self.dir)
        self.assertEqual(emails, set())
        self.assertEqual(domains, {d.lower() for d in common.PROFILE['company']['own_domains']})

    def test_register_blocks_by_status(self):
        write_csv(self.dir / 'contacts.csv', contacts.COLUMNS, [
            ['L1', 'A', '', '', '', 'ann@alpha.example.com', 'alpha.example.com', '', '', '', 'sent', '', '', ''],
            ['L2', 'B', '', '', '', 'bo@beta.example.com', 'beta.example.com', '', '', '', 'found', '', '', ''],
            ['L3', 'C', '', '', '', 'cy@gmail.com', '', '', '', '', 'bounced', '', '', '']])
        domains, emails = common.already_contacted(self.dir)
        self.assertIn('alpha.example.com', domains)
        self.assertIn('ann@alpha.example.com', emails)
        self.assertNotIn('beta.example.com', domains)  # "found" is not contact
        self.assertIn('cy@gmail.com', emails)
        self.assertNotIn('gmail.com', domains)  # a free mailbox blocks the address, never the provider

    def test_suppress_list_emails_domains_and_comments(self):
        (self.dir / 'suppress.txt').write_text('# do not contact\nstop@delta.example.com  # asked on the phone\n'
                                               'epsilon.example.org\n@zeta.example.net\n\n', encoding='utf-8')
        domains, emails = common.already_contacted(self.dir)
        self.assertIn('stop@delta.example.com', emails)
        self.assertIn('delta.example.com', domains)
        self.assertIn('epsilon.example.org', domains)
        self.assertIn('zeta.example.net', domains)

    def test_import_any_csv_with_email_or_domain_column(self):
        (self.dir / 'imports').mkdir()
        write_csv(self.dir / 'imports' / 'crm.csv', ['Name', 'Email', 'Notes'], [['Eve', 'Eve@Eta.example.com', 'x']])
        write_csv(self.dir / 'imports' / 'sites.csv', ['company', 'Website'], [['Theta', 'https://www.theta.example.org/about']])
        write_csv(self.dir / 'imports' / 'unrelated.csv', ['a', 'b'], [['no', 'columns']])
        domains, emails = common.already_contacted(self.dir)
        self.assertIn('eve@eta.example.com', emails)
        self.assertIn('eta.example.com', domains)
        self.assertIn('theta.example.org', domains)

    def test_earlier_campaign_exports_count(self):
        camp = self.dir / 'old-campaign'
        camp.mkdir()
        (camp / 'exported.jsonl').write_text(json.dumps({'id': 'L1', 'domain': 'iota.example.com', 'to': 'info@iota.example.com'}) + '\n')
        domains, emails = common.already_contacted(self.dir)
        self.assertIn('iota.example.com', domains)
        self.assertIn('info@iota.example.com', emails)


class Register(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / 'contacts.csv'

    def test_mark_creates_row_and_blocks(self):
        self.assertEqual(contacts.mark('Bob@Kappa.example.com', 'sent', 'batch 1', self.path), 1)
        rows = contacts.read_register(self.path)
        self.assertEqual(rows[0]['status'], 'sent')
        self.assertTrue(rows[0]['sent_date'])
        domains, emails = common.already_contacted(self.path.parent)
        self.assertIn('bob@kappa.example.com', emails)

    def test_mark_domain_blocks_the_domain(self):
        contacts.mark('lambda.example.com', 'blocked', path=self.path)
        domains, _ = common.already_contacted(self.path.parent)
        self.assertIn('lambda.example.com', domains)

    def test_merge_never_downgrades_a_status(self):
        rows = []
        contacts.merge(rows, {'email': 'a@mu.example.com', 'status': 'replied', 'company': 'Mu'})
        contacts.merge(rows, {'email': 'a@mu.example.com', 'status': 'queued', 'company': 'Mu again', 'city': 'Springfield'})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['status'], 'replied')
        self.assertEqual(rows[0]['company'], 'Mu')          # existing non-empty fields stay
        self.assertEqual(rows[0]['city'], 'Springfield')    # empty ones are filled

    def test_merge_upgrades_found_to_queued(self):
        rows = []
        contacts.merge(rows, {'email': 'a@nu.example.com', 'status': 'found'})
        contacts.merge(rows, {'email': 'a@nu.example.com', 'status': 'queued'})
        self.assertEqual(rows[0]['status'], 'queued')

    def test_bad_status_is_refused(self):
        with self.assertRaises(ValueError):
            contacts.mark('x@y.example.com', 'maybe', path=self.path)


if __name__ == '__main__':
    unittest.main()
