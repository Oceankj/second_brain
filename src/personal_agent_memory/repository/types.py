from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

import psycopg

Connect = Callable[[], AbstractAsyncContextManager[psycopg.AsyncConnection]]
