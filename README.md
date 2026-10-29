# outline-docker

English | [日本語](README_ja.md)

Run Outline and its dependencies—PostgreSQL, Redis, and Dex—with Docker Compose.
Dex handles user authentication for Outline. User accounts are stored in `dex/users.env`

| Purpose | URL |
| --- | --- |
| Outline | `http://localhost:3000` |
| Dex login | `http://localhost:5556/dex` |

## Data Storage

| Directory | Contents |
| --- | --- |
| `data/postgres/` | PostgreSQL database files, including `18/docker/` for PostgreSQL 18 |
| `data/dex/` | Dex SQLite database, signing keys, and related data |
| `data/outline/` | Document attachments |
| `data/redis/` | Persistent Redis data |

These data files are owned by UID 1001 / GID 1001, so copying them on the host may require `sudo`.

## Initial Setup

Install Docker, Docker Compose, and Python.
Make sure no other programs are using TCP ports 3000 and 5556 on the host.

1. Prepare and edit the configuration file.

```sh
cp .env.example .env
chmod 600 .env
```

Set `POSTGRES_PASSWORD`, `SECRET_KEY`, and `UTILS_SECRET` in `.env` to separate values, each generated with `openssl rand -hex 32`.

2. Create the first local user.

```sh
python3 scripts/dex-users.py add user@example.com --name "Your name" --no-apply
```

Enter the password in the terminal when prompted.
The email address is used only to identify the user; email verification is not performed.

## User Management

```sh
# List users
python3 scripts/dex-users.py list
# Add a user
python3 scripts/dex-users.py add alice@example.com --name "Alice"
# Change a password
python3 scripts/dex-users.py passwd alice@example.com
# Delete a user
python3 scripts/dex-users.py delete alice@example.com
```

- Adding a user, changing a password, or deleting a user briefly stops the authentication service.
- The last remaining user cannot be deleted.
- A new user's Outline account is created when they first sign in.
- Manage workspace invitations and permissions in Outline.
- Deleting a user in Dex does not delete their Outline account. To delete that account as well, use **Settings → Users** in Outline.
- Add `--no-apply` to skip restarting Dex. After making several changes, run `apply` to apply them together.

```sh
python3 scripts/dex-users.py add alice@example.com --name "Alice" --no-apply
python3 scripts/dex-users.py add bob@example.com --name "Bob" --no-apply
python3 scripts/dex-users.py apply
```

## Start and Sign In

```sh
docker compose up -d
```

Open `http://localhost:3000`, select **Local account**, and sign in with the email address and password configured using the script. On first use, follow Outline's instructions to create a workspace.

## Updates

Update `OUTLINE_VERSION` or `DEX_VERSION` in `.env`, then run `docker compose pull` and `docker compose up -d`.
If a database migration takes place, reverting to the previous image alone may not restore the data.
Back up your data before updating.

## References

- [Outline OIDC configuration](https://docs.getoutline.com/s/hosting/doc/oidc-8CPBm6uC0I)
- [Dex local users](https://dexidp.io/docs/connectors/local/)
- [Dex storage](https://dexidp.io/docs/configuration/storage/)
- [Dex official Docker configuration](https://github.com/dexidp/dex/blob/v2.46.1/config.docker.yaml)
