import importlib
import subprocess
import sys
import unittest

import helpers
from helpers import ROOT, SCRIPTS

MODULES = ['common', 'mail', 'quality', 'discover', 'scan', 'registry', 'score', 'draft', 'verify', 'export', 'report',
           'status', 'coverage', 'contacts', 'prospect', 'doctor']
CLI_SCRIPTS = ['discover', 'scan', 'registry', 'score', 'draft', 'verify', 'export', 'report', 'status', 'coverage',
               'contacts', 'prospect', 'doctor']


class Smoke(unittest.TestCase):
    def test_every_script_imports(self):
        for name in MODULES:
            with self.subTest(module=name):
                importlib.import_module(name)

    def test_every_script_answers_help(self):
        for name in CLI_SCRIPTS:
            with self.subTest(script=name):
                r = subprocess.run([sys.executable, str(SCRIPTS / f'{name}.py'), '--help'], capture_output=True, text=True, timeout=60)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertTrue(r.stdout.strip())

    def test_profiles_are_valid_json_sets(self):
        import common
        for prof in ('example-translation-agency', '_template'):
            with self.subTest(profile=prof):
                loaded = common.load_profile(ROOT / 'profiles' / prof)
                self.assertTrue(loaded['sectors']['sectors'])
                self.assertIsInstance(loaded['signals'], list)

    def test_template_is_blank_and_example_is_complete(self):
        import common
        self.assertTrue(common.placeholders(common.load_profile(ROOT / 'profiles' / '_template')['profile']))
        self.assertEqual(common.profile_placeholders(), [])  # the default (example) profile has none

    def test_every_sector_has_what_the_pipeline_needs(self):
        import common
        for s in common.load_sectors():
            with self.subTest(sector=s['id']):
                self.assertIn(s['offer'], common.VARIANTS['offers'])
                for loc in common.LOCALES:
                    self.assertTrue(s['subject'].get(loc) and s['block'].get(loc))
                    for variant in common.VARIANTS['offers'][s['offer']].values():
                        self.assertEqual(len(variant[loc]), 2)

    def test_bad_profile_is_a_clear_error(self):
        r = subprocess.run([sys.executable, str(SCRIPTS / 'score.py'), '--campaign', 'x', '--profile', 'no-such-profile'],
                           capture_output=True, text=True, timeout=60)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('profile', (r.stdout + r.stderr).lower())

    def test_doctor_is_graceful_without_network_checks_failing_the_run(self):
        r = subprocess.run([sys.executable, str(SCRIPTS / 'doctor.py')], capture_output=True, text=True, timeout=180)
        self.assertIn(r.returncode, (0, 1))
        self.assertIn('python', r.stdout)


if __name__ == '__main__':
    unittest.main()
