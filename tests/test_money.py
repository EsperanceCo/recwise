from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recwise.money import (
    InvalidAmountError,
    bank_amount_to_signed,
    format_decimal_comma,
    format_decimal_dot,
    parse_amount,
    round_money,
)


def test_round_money_half_up() -> None:
    assert round_money(Decimal("1.005")) == Decimal("1.01")
    assert round_money(Decimal("1.004")) == Decimal("1.00")
    # ROUND_HALF_UP rounds ties away from zero, so this rounds to -1.01, not -1.00.
    assert round_money(Decimal("-1.005")) == Decimal("-1.01")


def test_parse_amount_plain_dot() -> None:
    assert parse_amount("1234.56") == Decimal("1234.56")
    assert parse_amount("-45.00") == Decimal("-45.00")
    assert parse_amount("0.5") == Decimal("0.50")


def test_parse_amount_decimal_comma_with_dot_thousands() -> None:
    assert parse_amount("1.234,56") == Decimal("1234.56")
    assert parse_amount("56,00") == Decimal("56.00")
    assert parse_amount("-1.234,56") == Decimal("-1234.56")


def test_parse_amount_comma_thousands_with_dot_decimal() -> None:
    assert parse_amount("1,234.56") == Decimal("1234.56")


def test_parse_amount_ambiguous_comma_as_decimal() -> None:
    # A single comma with != 3 fraction digits must be a decimal separator.
    assert parse_amount("12,5") == Decimal("12.50")


def test_parse_amount_empty_raises() -> None:
    with pytest.raises(InvalidAmountError):
        parse_amount("")
    with pytest.raises(InvalidAmountError):
        parse_amount("   ")


def test_parse_amount_garbage_raises() -> None:
    with pytest.raises(InvalidAmountError):
        parse_amount("not-a-number")


def test_format_decimal_dot() -> None:
    assert format_decimal_dot(Decimal("1234.5")) == "1234.50"


def test_format_decimal_comma() -> None:
    assert format_decimal_comma(Decimal("1234.5")) == "1.234,50"
    assert format_decimal_comma(Decimal("-56")) == "-56,00"
    assert format_decimal_comma(Decimal("42")) == "42,00"


def test_bank_amount_to_signed_credit_is_ledger_debit() -> None:
    assert bank_amount_to_signed(None, Decimal("100.00")) == Decimal("100.00")


def test_bank_amount_to_signed_debit_is_ledger_credit() -> None:
    assert bank_amount_to_signed(Decimal("100.00"), None) == Decimal("-100.00")


def test_bank_amount_to_signed_rejects_negative_columns() -> None:
    with pytest.raises(InvalidAmountError):
        bank_amount_to_signed(Decimal("-1.00"), None)


@given(
    value=st.decimals(
        min_value=Decimal("-999999.99"),
        max_value=Decimal("999999.99"),
        places=2,
        allow_nan=False,
        allow_infinity=False,
    )
)
def test_decimal_comma_round_trip(value: Decimal) -> None:
    formatted = format_decimal_comma(value)
    assert parse_amount(formatted) == round_money(value)


@given(
    value=st.decimals(
        min_value=Decimal("-999999.99"),
        max_value=Decimal("999999.99"),
        places=2,
        allow_nan=False,
        allow_infinity=False,
    )
)
def test_decimal_dot_round_trip(value: Decimal) -> None:
    formatted = format_decimal_dot(value)
    assert parse_amount(formatted) == round_money(value)
