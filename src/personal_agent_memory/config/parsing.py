from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def config_section(config: Mapping[str, Any], section: str) -> Mapping[str, Any]:
    section_values = config.get(section, {})
    if section_values is None:
        return {}
    if not isinstance(section_values, Mapping):
        raise ValueError(f"memory.json {section} must be an object")
    return section_values


def config_int(
    config: Mapping[str, Any],
    *,
    section: str,
    key: str,
    default: int,
) -> int:
    section_values = config_section(config, section)
    return config_int_from_section(section_values, key=key, default=default)


def config_int_from_section(
    section_values: Mapping[str, Any],
    *,
    key: str,
    default: int,
) -> int:
    value = section_values.get(key)
    if value is None:
        value = default
    return int(value)


def config_float(
    config: Mapping[str, Any],
    *,
    section: str,
    key: str,
    default: float,
) -> float:
    section_values = config_section(config, section)
    return config_float_from_section(section_values, key=key, default=default)


def config_float_from_section(
    section_values: Mapping[str, Any],
    *,
    key: str,
    default: float,
) -> float:
    value = section_values.get(key)
    if value is None:
        value = default
    return float(value)


def config_str(section_values: Mapping[str, Any], *, key: str, default: str) -> str:
    value = section_values.get(key)
    if value is None:
        value = default
    return str(value)


def config_optional_str(section_values: Mapping[str, Any], *, key: str) -> str | None:
    value = section_values.get(key)
    if value is None:
        return None
    return str(value)


def config_str_tuple(
    section_values: Mapping[str, Any],
    *,
    key: str,
    default: tuple[str, ...],
) -> tuple[str, ...]:
    value = section_values.get(key)
    if value is None:
        return default
    if not isinstance(value, list | tuple):
        raise ValueError(f"memory.json {key} must be a list")
    return tuple(str(item) for item in value)


def config_bool_from_section(
    section_values: Mapping[str, Any],
    *,
    key: str,
    default: bool,
) -> bool:
    raw_value = section_values.get(key)
    if raw_value is None:
        return default
    if isinstance(raw_value, bool):
        return raw_value
    return parse_bool(str(raw_value), name=f"memory.json {key}")


def parse_bool(raw_value: str, *, name: str) -> bool:
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")
