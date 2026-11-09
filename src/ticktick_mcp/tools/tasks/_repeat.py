from __future__ import annotations

from fastmcp.exceptions import ToolError

from ticktick_mcp.tools.tasks._common import RRULE_FREQS, RRULE_KEYS, WEEKDAYS


def _normalize_repeat_rule(repeat: str) -> str:
    rule = repeat.strip().upper()
    if not rule.startswith("RRULE:"):
        raise ToolError("Repeat must be an RRULE string beginning with 'RRULE:'")

    body = rule.removeprefix("RRULE:")
    if not body:
        raise ToolError("Repeat RRULE must include FREQ")

    parts: dict[str, str] = {}
    for part in body.split(";"):
        if not part or "=" not in part:
            raise ToolError("Repeat RRULE parts must use KEY=VALUE")
        key, value = part.split("=", 1)
        if not key or not value:
            raise ToolError("Repeat RRULE parts must use KEY=VALUE")
        if key not in RRULE_KEYS:
            raise ToolError(f"Unsupported RRULE part '{key}'")
        if key in parts:
            raise ToolError(f"Duplicate RRULE part '{key}'")
        parts[key] = value

    freq = parts.get("FREQ")
    if freq not in RRULE_FREQS:
        raise ToolError("Repeat RRULE requires FREQ=DAILY, WEEKLY, MONTHLY, or YEARLY")

    for key in ("INTERVAL", "COUNT"):
        if key in parts and (not parts[key].isdigit() or int(parts[key]) <= 0):
            raise ToolError(f"RRULE {key} must be a positive integer")

    if "BYMONTH" in parts:
        _validate_rrule_int_list("BYMONTH", parts["BYMONTH"], 1, 12)
    if "BYMONTHDAY" in parts:
        _validate_rrule_int_list("BYMONTHDAY", parts["BYMONTHDAY"], 1, 31)
    if "BYDAY" in parts:
        _validate_rrule_byday(parts["BYDAY"])
    if "WKST" in parts and parts["WKST"] not in WEEKDAYS:
        raise ToolError("RRULE WKST must be one of MO, TU, WE, TH, FR, SA, SU")

    return "RRULE:" + ";".join(f"{key}={value}" for key, value in parts.items())


def _validate_rrule_int_list(key: str, value: str, minimum: int, maximum: int) -> None:
    for item in value.split(","):
        if not item.isdigit():
            raise ToolError(f"RRULE {key} must contain integers")
        number = int(item)
        if number < minimum or number > maximum:
            raise ToolError(f"RRULE {key} values must be between {minimum} and {maximum}")


def _validate_rrule_byday(value: str) -> None:
    for item in value.split(","):
        day = item[-2:]
        prefix = item[:-2]
        if day not in WEEKDAYS:
            raise ToolError("RRULE BYDAY must use weekdays MO, TU, WE, TH, FR, SA, SU")
        if prefix and (not prefix.lstrip("+-").isdigit() or int(prefix) == 0):
            raise ToolError("RRULE BYDAY ordinals must be non-zero integers")


def _normalize_repeat_from(repeat_from: str | None) -> str:
    if repeat_from is None:
        return "1"
    value = repeat_from.strip().lower()
    if value in {"1", "due", "due_date", "due-date"}:
        return "1"
    raise ToolError("repeat_from currently supports only due_date")
