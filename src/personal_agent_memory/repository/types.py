from __future__ import annotations

from collections.abc import Awaitable, Callable

import psycopg

Connect = Callable[[], Awaitable[psycopg.AsyncConnection]]
