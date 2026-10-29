#!/usr/bin/env python3
"""Manage Dex static users with only Python's standard library and Docker."""
import argparse
import fcntl
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parent.parent
USERS = ROOT / 'dex/users.env'
ENV = ROOT / '.env'


def atomic_write(path, content):
    fd, name = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(content)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def env_values():
    # Read the simple dotenv values written by the previous single-user setup.
    if not ENV.exists():
        return {}
    values = {}
    for line in ENV.read_text().splitlines():
        key, sep, value = line.partition('=')
        if sep and not key.startswith('#'):
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1].replace("\\'", "'").replace('\\\\', '\\')
            values[key.strip()] = value
    return values


def load_users():
    if USERS.exists():
        text = USERS.read_text().strip()
        prefix = "DEX_USERS_JSON='"
        if not text.startswith(prefix) or not text.endswith("'"):
            raise ValueError('Invalid dex/users.env format; do not edit it by hand.')
        users = json.loads(text[len(prefix):-1])
    else:
        old = env_values()
        required = ['DEX_USER_EMAIL', 'DEX_USER_ID', 'DEX_PASSWORD_HASH']
        if all(old.get(k) for k in required):
            users = [dict(email=old['DEX_USER_EMAIL'], userID=old['DEX_USER_ID'],
                          username=old.get('DEX_USER_NAME') or 'Local user', hash=old['DEX_PASSWORD_HASH'])]
        else:
            users = []
    if not isinstance(users, list):
        raise ValueError('User data must be a list.')
    emails, ids = set(), set()
    for user in users:
        if not isinstance(user, dict) or any(not isinstance(user.get(k), str) or not user[k] for k in ('email', 'userID', 'username', 'hash')):
            raise ValueError('Invalid user entry.')
        if user['email'].casefold() in emails or user['userID'] in ids:
            raise ValueError('Duplicate email or user ID.')
        emails.add(user['email'].casefold()); ids.add(user['userID'])
    return users


def save_users(users):
    # JSON as a single-quoted dotenv value preserves bcrypt's dollar signs.
    # Encode apostrophes so arbitrary display names cannot end the dotenv quote.
    encoded = json.dumps(users, ensure_ascii=True, separators=(',', ':')).replace("'", '\\u0027')
    atomic_write(USERS, "DEX_USERS_JSON='" + encoded + "'\n")


def ensure_secret():
    if not ENV.exists():
        atomic_write(ENV, (ROOT / '.env.example').read_text())
    if not env_values().get('OIDC_CLIENT_SECRET'):
        lines = [line for line in ENV.read_text().splitlines() if not line.startswith('OIDC_CLIENT_SECRET=')]
        lines.append('OIDC_CLIENT_SECRET=' + secrets.token_hex(32))
        atomic_write(ENV, '\n'.join(lines) + '\n')


def password_hash():
    password = getpass.getpass('Password: ')
    if not password or password != getpass.getpass('Confirm password: '):
        raise ValueError('Passwords are empty or do not match.')
    if len(password.encode()) > 72 or '\n' in password or '\r' in password:
        raise ValueError('Use at most 72 UTF-8 bytes without newlines.')
    try:
        result = subprocess.run(['docker', 'run', '--rm', '-i', 'httpd:2.4-alpine',
                                 'htpasswd', '-niBC', '12', 'dex'],
                                input=password + '\n', text=True, capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        raise ValueError('Cannot generate bcrypt hash. Check Docker access and image download.') from None
    hashed = result.stdout.strip().split(':', 1)[-1]
    if not re.fullmatch(r'\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}', hashed):
        raise ValueError('Unexpected htpasswd output; user data was not changed.')
    return hashed


def validate_email(email):
    email = email.strip()
    if not re.fullmatch(r'[^\s@]+@[^\s@]+', email):
        raise ValueError('Enter a valid email address.')
    return email


def find_user(users, email):
    return next((u for u in users if u['email'].casefold() == email.casefold()), None)


def apply():
    try:
        subprocess.run(['docker', 'compose', 'up', '-d', '--no-deps', '--force-recreate', 'dex'], cwd=ROOT, check=True)
    except (OSError, subprocess.CalledProcessError):
        raise ValueError('Settings were saved, but applying them failed. Run: python3 scripts/dex-users.py apply') from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list', help='List email, display name and stable user ID; no password hashes')
    commands.add_parser('apply', help='Recreate Dex to load saved users')
    for command in ('migrate', 'add', 'passwd', 'delete'):
        sub = commands.add_parser(command)
        sub.add_argument('--no-apply', action='store_true', help='Save only; apply later')
        if command in ('add', 'passwd', 'delete'):
            sub.add_argument('email')
        if command == 'add':
            sub.add_argument('--name', default='Local user')
    args = parser.parse_args(argv)
    # Lock the management file independently of atomic replacement of users.env.
    lock = ROOT / 'dex/.users.lock'
    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, 'w') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        users = load_users()
        if args.command == 'list':
            for u in users:
                print(f"{u['email']}\t{u['username']}\t{u['userID']}")
            if not users:
                print('No users. Run: python3 scripts/dex-users.py add EMAIL --no-apply')
            return
        if args.command == 'apply':
            if not USERS.exists():
                raise ValueError('Run add or migrate first.')
            apply()
            return
        if args.command == 'migrate' and not users:
            raise ValueError('No legacy user found in .env. Run add instead.')
        if args.command == 'add':
            email = validate_email(args.email)
            if find_user(users, email):
                raise ValueError('Email already exists. Use passwd to change its password.')
            if not args.name.strip():
                raise ValueError('Display name must not be empty.')
            users.append(dict(email=email, username=args.name, userID=str(uuid.uuid4()), hash=password_hash()))
        elif args.command in ('passwd', 'delete'):
            user = find_user(users, args.email)
            if user is None:
                raise ValueError('User not found.')
            if args.command == 'delete':
                if len(users) == 1:
                    raise ValueError('Cannot delete the last user; add another user first.')
                users.remove(user)
            else:
                user['hash'] = password_hash()
        ensure_secret()
        save_users(users)
        print('Saved dex/users.env.')
        if not args.no_apply:
            apply()
        else:
            print('Run: python3 scripts/dex-users.py apply (or docker compose up -d for first startup)')
        if args.command == 'delete':
            print('Existing Outline sessions remain. Suspend the user in Outline Settings > Users to revoke access immediately.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        raise SystemExit(str(error))
