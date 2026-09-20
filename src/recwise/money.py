"""Money handling: Decimal parsing, rounding, and the sign convention.

Every module that touches an amount goes through this one. Nothing else in
the codebase should call `round()` on money or re-derive how a bank
statement's debit/credit columns map onto the ledger's signed amount.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

TWO_PLACES = Decimal("0.01")

# Sign convention (the ONE place this is defined; see CLAUDE.md "Money" rules):
#
#   Ledger (cash book): a single signed `amount`.
#       positive = debit  = cash inflow  (increases the cash balance)
#       negative = credit = cash outflow (decreases the cash balance)
#
#   Bank statement: separate `debit` and `credit` columns, both non-negative.
#       `credit` = money added to the account   -> equivalent to a ledger debit (positive)
#       `debit`  = money removed from the account -> equivalent to a ledger credit (negative)
#
#   In one sentence: a bank credit is a ledger debit. `bank_amount_to_signed`
#   below is the only place that conversion happens.


class InvalidAmountError(ValueError):
    """Raised when a string cannot be parsed as a money amount."""


def round_money(value: Decimal) -> Decimal:
    """Round a Decimal to 2 places using ROUND_HALF_UP. The only rounding helper."""
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


_DOT_DECIMAL_RE = re.compile(r"^-?\d{1,3}(,\d{3})*(\.\d+)?$|^-?\d+(\.\d+)?$")
_COMMA_DECIMAL_RE = re.compile(r"^-?\d{1,3}(\.\d{3})*(,\d+)?$|^-?\d+(,\d+)?$")


def parse_amount(raw: str) -> Decimal:
    """Parse a money string into a Decimal, auto-detecting the decimal separator.

    Handles both "1,234.56" (decimal dot, comma thousands) and "1.234,56"
    (decimal comma, dot thousands) styles, plus plain "1234.56" / "1234,56"
    / "-45.00" with no thousands separator at all.
    """
    cleaned = raw.strip()
    if not cleaned:
        raise InvalidAmountError(f"empty amount string: {raw!r}")

    negative = False
    if cleaned.startswith("-"):
        negative = True
        cleaned = cleaned[1:].strip()
    elif cleaned.startswith("+"):
        cleaned = cleaned[1:].strip()

    if not cleaned:
        raise InvalidAmountError(f"empty amount string: {raw!r}")

    has_dot = "." in cleaned
    has_comma = "," in cleaned

    if has_dot and has_comma:
        # Whichever separator appears last is the decimal point.
        if cleaned.rfind(",") > cleaned.rfind("."):
            digits = cleaned.replace(".", "").replace(",", ".")
        else:
            digits = cleaned.replace(",", "")
    elif has_comma and not has_dot:
        # Ambiguous: "1,234" (thousands) vs "1234,56" (decimal comma).
        # Treat a comma followed by exactly 3 digits with no other comma as
        # thousands only when there are 4+ digits before it; otherwise decimal.
        parts = cleaned.split(",")
        if len(parts) == 2 and len(parts[1]) != 3:
            digits = cleaned.replace(",", ".")
        elif len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) <= 3:
            # e.g. "1,234" -> thousands separator, no decimal part
            digits = cleaned.replace(",", "")
        else:
            digits = cleaned.replace(",", ".")
    elif has_dot and not has_comma:
        parts = cleaned.split(".")
        if len(parts) == 2 and len(parts[1]) != 3:
            digits = cleaned
        elif len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) <= 3:
            # e.g. "1.234" -> thousands separator, no decimal part
            digits = cleaned.replace(".", "")
        else:
            digits = cleaned
    else:
        digits = cleaned

    try:
        value = Decimal(digits)
    except InvalidOperation as exc:
        raise InvalidAmountError(f"cannot parse amount: {raw!r}") from exc

    if negative:
        value = -value
    return round_money(value)


def format_decimal_dot(value: Decimal) -> str:
    """Format a Decimal as plain dot-decimal, e.g. Decimal('1234.5') -> '1234.50'."""
    return str(round_money(value))


def format_decimal_comma(value: Decimal) -> str:
    """Format a Decimal with dot thousands separators and a comma decimal point.

    Decimal('1234.5') -> '1.234,50'; Decimal('-56') -> '-56,00'.
    """
    quantized = round_money(value)
    negative = quantized < 0
    whole, _, frac = f"{abs(quantized):.2f}".partition(".")
    grouped = f"{int(whole):,}".replace(",", ".")
    sign = "-" if negative else ""
    return f"{sign}{grouped},{frac}"


def bank_amount_to_signed(debit: Decimal | None, credit: Decimal | None) -> Decimal:
    """Convert a bank statement's debit/credit columns to a signed ledger-style amount.

    This is the single conversion point for the "bank credit = ledger debit"
    sign convention documented above.
    """
    debit_value = debit if debit is not None else Decimal("0")
    credit_value = credit if credit is not None else Decimal("0")
    if debit_value < 0 or credit_value < 0:
        raise InvalidAmountError("bank debit/credit columns must be non-negative")
    return round_money(credit_value - debit_value)
