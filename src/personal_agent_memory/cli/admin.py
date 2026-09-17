from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import sys
import warnings
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from personal_agent_memory.config import load_dotenv
from personal_agent_memory.repository.users import UsersRepository
from personal_agent_memory.services.users import hash_password, normalize_username


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Manage closed-registration memory accounts.")
    result.add_argument("--env-file", type=Path, help="Defaults to .env in the current directory")
    commands = result.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-user", help="Create an account with a generated user ID")
    create.add_argument("username", nargs="?", help="Prompted if omitted; stored lowercase")
    create.add_argument("--display-name")
    for name in ("set-password", "disable-user", "enable-user"):
        command = commands.add_parser(name)
        command.add_argument("username")
    commands.add_parser("list-users", help="List accounts without credentials (JSON)")
    return result


def read_password() -> str:
    # Refuse getpass's visible-input fallback when a secure terminal is unavailable.
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        password = getpass.getpass("Password: ")
        confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise ValueError("Passwords do not match.")
    if not 10 <= len(password) <= 1024 or len(set(password)) < 4:
        raise ValueError("Use 10–1024 characters with at least 4 distinct characters.")
    return password


async def run(args: argparse.Namespace, users: UsersRepository) -> None:
    if args.command == "list-users":
        print(json.dumps(await users.list_logins(), ensure_ascii=True, indent=2))
        return
    username = normalize_username(args.username or input("Username: "))
    if args.command == "create-user":
        encoded = hash_password(read_password())
        user = await users.create_login(str(uuid4()), username, encoded, args.display_name)
        print(json.dumps(user, ensure_ascii=True))
    elif args.command == "set-password":
        encoded = hash_password(read_password())
        if not await users.set_password(username, encoded):
            raise ValueError("User not found.")
        print("Password updated.")
    else:
        active = args.command == "enable-user"
        if not await users.set_active(username, active):
            raise ValueError("User not found.")
        print("User enabled." if active else "User disabled.")


def main() -> None:
    args = parser().parse_args()
    try:
        load_dotenv(args.env_file)
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL is required.")

        @asynccontextmanager
        async def connect() -> AsyncIterator[psycopg.AsyncConnection]:
            async with await psycopg.AsyncConnection.connect(
                database_url, row_factory=dict_row, connect_timeout=15, prepare_threshold=None
            ) as conn:
                yield conn

        asyncio.run(run(args, UsersRepository(connect)))
    except psycopg.errors.UniqueViolation:
        print("Error: Username already exists (case-insensitive).", file=sys.stderr)
        raise SystemExit(1) from None
    except psycopg.Error:
        # Database errors can contain SQL parameters, connection credentials or hashes.
        print(
            "Error: Database operation failed; check connectivity and migrations.", file=sys.stderr
        )
        raise SystemExit(1) from None
    except getpass.GetPassWarning:
        print("Error: A terminal with hidden password input is required.", file=sys.stderr)
        raise SystemExit(1) from None
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    except (EOFError, KeyboardInterrupt):
        print("Cancelled.", file=sys.stderr)
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
