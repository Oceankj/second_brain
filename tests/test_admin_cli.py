import getpass
import warnings
from unittest.mock import AsyncMock

import psycopg
import pytest

from personal_agent_memory.cli import admin
from personal_agent_memory.services.users import verify_password


@pytest.fixture
def users():
    return AsyncMock()


def passwords(monkeypatch, first="a long private passphrase", second=None):
    answers = iter([first, first if second is None else second])
    monkeypatch.setattr(admin.getpass, "getpass", lambda prompt: next(answers))


@pytest.mark.anyio
async def test_create_user_prompts_and_hashes_password(monkeypatch, capsys, users):
    passwords(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda prompt: "ALICE")
    users.create_login.return_value = {"id": "new-id", "username": "alice"}
    await admin.run(admin.parser().parse_args(["create-user"]), users)
    user_id, username, encoded, display_name = users.create_login.call_args.args
    assert user_id != "0"
    assert username == "alice"
    assert display_name is None
    assert verify_password("a long private passphrase", encoded)
    output = capsys.readouterr().out
    assert "alice" in output
    assert encoded not in output
    assert "private passphrase" not in output


@pytest.mark.anyio
async def test_set_password_does_not_enable_or_create_user(monkeypatch, users):
    passwords(monkeypatch)
    users.set_password.return_value = True
    await admin.run(admin.parser().parse_args(["set-password", "ADMIN"]), users)
    username, encoded = users.set_password.call_args.args
    assert username == "admin"
    assert verify_password("a long private passphrase", encoded)
    users.set_active.assert_not_called()
    users.create_login.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("command,active", [("disable-user", False), ("enable-user", True)])
async def test_enable_disable_are_case_insensitive(command, active, users):
    users.set_active.return_value = True
    await admin.run(admin.parser().parse_args([command, "ALIce"]), users)
    users.set_active.assert_awaited_once_with("alice", active)


@pytest.mark.anyio
@pytest.mark.parametrize("command", ["set-password", "disable-user", "enable-user"])
async def test_missing_user_is_rejected(command, monkeypatch, users):
    passwords(monkeypatch)
    users.set_active.return_value = False
    users.set_password.return_value = False
    with pytest.raises(ValueError, match="User not found"):
        await admin.run(admin.parser().parse_args([command, "missing"]), users)


@pytest.mark.anyio
@pytest.mark.parametrize("password,confirmation", [
    ("short", "short"),
    ("a" * 20, "a" * 20),
    ("abcd" * 257, "abcd" * 257),
    ("a long private passphrase", "different"),
])
async def test_invalid_passwords_do_not_write(password, confirmation, monkeypatch, users):
    passwords(monkeypatch, password, confirmation)
    with pytest.raises(ValueError):
        await admin.run(admin.parser().parse_args(["create-user", "alice"]), users)
    users.create_login.assert_not_called()


def test_visible_password_fallback_is_refused(monkeypatch):
    def visible_input(prompt):
        warnings.warn("Cannot hide input", getpass.GetPassWarning, stacklevel=2)
        pytest.fail("Must not proceed with visible input")
    monkeypatch.setattr(admin.getpass, "getpass", visible_input)
    with pytest.raises(getpass.GetPassWarning):
        admin.read_password()


@pytest.mark.anyio
async def test_list_users_does_not_prompt(monkeypatch, users, capsys):
    users.list_logins.return_value = [{"id": "0", "username": "admin",
                                      "password_configured": False}]
    monkeypatch.setattr(admin.getpass, "getpass", lambda prompt: pytest.fail("Unexpected prompt"))
    await admin.run(admin.parser().parse_args(["list-users"]), users)
    assert '"password_configured": false' in capsys.readouterr().out


@pytest.mark.parametrize("error,expected", [
    (psycopg.errors.UniqueViolation("sensitive details"), "Username already exists"),
    (psycopg.OperationalError("sensitive details"), "Database operation failed"),
])
def test_database_errors_are_redacted(monkeypatch, capsys, error, expected):
    monkeypatch.setattr("sys.argv", ["memory-admin", "list-users"])
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setattr(admin, "load_dotenv", lambda path: None)
    monkeypatch.setattr(admin, "run", AsyncMock(side_effect=error))
    with pytest.raises(SystemExit) as exc:
        admin.main()
    assert exc.value.code == 1
    output = capsys.readouterr().err
    assert expected in output
    assert "sensitive details" not in output


def test_password_argument_is_not_supported():
    with pytest.raises(SystemExit):
        admin.parser().parse_args(["set-password", "alice", "--password", "secret"])
