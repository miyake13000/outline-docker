import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/dex-users.py'
spec = importlib.util.spec_from_file_location('dex_users', SCRIPT)
users = importlib.util.module_from_spec(spec)
spec.loader.exec_module(users)
HASH = '$2y$12$' + 'A' * 53


class UserManagementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / 'dex').mkdir()
        (root / '.env').write_text('OIDC_CLIENT_SECRET=keep-this-secret\nSECRET_KEY=keep-this-key\n')
        for attr, value in [('ROOT', root), ('ENV', root / '.env'), ('USERS', root / 'dex/users.env')]:
            patcher = patch.object(users, attr, value)
            patcher.start(); self.addCleanup(patcher.stop)
        self.output = io.StringIO()

    def run_cli(self, *args):
        with contextlib.redirect_stdout(self.output):
            users.main(args)

    def add(self, email, name='User'):
        with patch.object(users, 'password_hash', return_value=HASH):
            self.run_cli('add', email, '--name', name, '--no-apply')

    def test_lifecycle_and_stable_ids(self):
        self.add('alice@example.com', "Alice's 日本語 $name")
        first_id = users.load_users()[0]['userID']
        self.add('bob@example.com')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.add('ALICE@example.com')
        with patch.object(users, 'password_hash', return_value='$2y$12$' + 'B' * 53):
            self.run_cli('passwd', 'ALICE@example.com', '--no-apply')
        self.assertEqual(users.load_users()[0]['userID'], first_id)
        self.assertEqual(users.load_users()[0]['username'], "Alice's 日本語 $name")
        self.run_cli('list')
        self.assertNotIn(HASH, self.output.getvalue())
        self.run_cli('delete', 'bob@example.com', '--no-apply')
        with self.assertRaisesRegex(ValueError, 'last user'):
            self.run_cli('delete', 'alice@example.com', '--no-apply')
        self.assertEqual(len(users.load_users()), 1)
        self.assertEqual(users.USERS.stat().st_mode & 0o777, 0o600)
        self.assertIn('keep-this-secret', users.ENV.read_text())

    def test_migration_preserves_id_hash_and_email(self):
        with users.ENV.open('a') as stream:
            stream.write("DEX_USER_EMAIL='old@example.com'\nDEX_USER_ID='existing-id'\nDEX_PASSWORD_HASH='" + HASH + "'\n")
        self.run_cli('migrate', '--no-apply')
        migrated = users.load_users()[0]
        self.assertEqual(migrated['userID'], 'existing-id')
        self.assertEqual(migrated['hash'], HASH)
        self.run_cli('migrate', '--no-apply')
        self.assertEqual(users.load_users()[0], migrated)

    def test_hashing_failure_does_not_change_users(self):
        self.add('alice@example.com')
        before = users.USERS.read_bytes()
        with patch('getpass.getpass', return_value='private-password'), patch('subprocess.run', side_effect=subprocess.CalledProcessError(1, 'docker')):
            with self.assertRaisesRegex(ValueError, 'Cannot generate'):
                self.run_cli('passwd', 'alice@example.com', '--no-apply')
        self.assertEqual(users.USERS.read_bytes(), before)

    def test_password_not_passed_in_arguments(self):
        with patch('getpass.getpass', return_value='private-password'), patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, 'dex:' + HASH + '\n')) as run:
            self.assertEqual(users.password_hash(), HASH)
        self.assertNotIn('private-password', run.call_args.args[0])
        self.assertEqual(run.call_args.kwargs['input'], 'private-password\n')

    def test_apply_failure_keeps_saved_changes(self):
        with patch.object(users, 'password_hash', return_value=HASH), patch('subprocess.run', side_effect=subprocess.CalledProcessError(1, 'docker')):
            with self.assertRaisesRegex(ValueError, 'saved, but applying'):
                self.run_cli('add', 'alice@example.com')
        self.assertEqual(users.load_users()[0]['email'], 'alice@example.com')

    def test_unknown_email_does_not_change_data(self):
        self.add('alice@example.com')
        before = users.USERS.read_bytes()
        with self.assertRaisesRegex(ValueError, 'not found'):
            self.run_cli('delete', 'nobody@example.com', '--no-apply')
        self.assertEqual(users.USERS.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
