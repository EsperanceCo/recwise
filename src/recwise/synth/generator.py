"""Synthetic ledger + bank statement generator with a known answer key.

Deterministic: the same seed always produces the same output. All amounts
are Decimal from the moment they're created; nothing here ever touches
`float`. See recwise.money for the sign convention.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from recwise.money import round_money
from recwise.synth.models import BankRow, Category, LedgerRow, PlantedCase

# Invented Azerbaijani-flavoured names. Fake on purpose: never realistic
# people or companies. Used only to exercise non-ASCII handling.
_PARTIES = [
    "Şəms MMC",
    "Günəş Ticarət MMC",
    "Xəzər Konsalting",
    "Ulduz Tekstil",
    "Nərgiz Dizayn Studiyası",
    "Öznur Xidmətləri",
    "Çinar Tikinti MMC",
    "Bahar Qida MMC",
    "Zümrüd Logistika",
    "İpək Yolu Ticarət",
    "Qızıl Balıq Restoranı",
    "Şəfəq Baytarlıq Kliniki",
]

_NORMAL_PHRASES = ["Ödəniş", "Mədaxil", "Fatura ödənişi", "Xidmət haqqı", "Malların dəyəri"]
_CHARGE_PHRASES = ["Bank komissiyası", "Hesab xidmət haqqı", "Kartın illik haqqı"]
_INTEREST_PHRASES = ["Faiz gəliri", "Depozit faizi"]
_DIRECT_DEBIT_PHRASES = ["Birbaşa debet", "Abunə ödənişi", "Kommunal ödəniş"]

TEST_ACCOUNT_PREFIX = "TEST"


@dataclass(frozen=True)
class SynthConfig:
    seed: int = 42
    count: int = 1000
    start_date: date = date(2024, 1, 1)
    num_days: int = 90


@dataclass
class GeneratedData:
    ledger_rows: list[LedgerRow]
    bank_rows: list[BankRow]
    cases: list[PlantedCase]
    config: SynthConfig


class _IdFactory:
    def __init__(self, prefix: str) -> None:
        self._prefix = prefix
        self._n = 0

    def next(self) -> str:
        self._n += 1
        return f"{self._prefix}-{self._n:06d}"


def _random_amount(rng: random.Random, low: str = "10.00", high: str = "5000.00") -> Decimal:
    low_cents = int(Decimal(low) * 100)
    high_cents = int(Decimal(high) * 100)
    cents = rng.randint(low_cents, high_cents)
    return round_money(Decimal(cents) / 100)


def _transpose_digits(rng: random.Random, amount: Decimal) -> Decimal:
    cents = int(round_money(amount) * 100)
    digits = list(str(cents))
    if len(digits) >= 3:
        candidates = [i for i in range(1, len(digits) - 1) if digits[i] != digits[i + 1]]
        if candidates:
            i = rng.choice(candidates)
            digits[i], digits[i + 1] = digits[i + 1], digits[i]
    new_cents = int("".join(digits))
    return round_money(Decimal(new_cents) / 100)


def _add_noise(rng: random.Random, text: str) -> str:
    """Apply messy-real-world-data noise: extra spaces, casing, truncation."""
    noisy = text
    roll = rng.random()
    if roll < 0.15:
        words = noisy.split(" ")
        idx = rng.randrange(len(words))
        words[idx] = words[idx].upper() if rng.random() < 0.5 else words[idx].lower()
        noisy = "  ".join(words)
    elif roll < 0.25:
        noisy = f"  {noisy} "
    elif roll < 0.35 and len(noisy) > 8:
        cut = rng.randint(6, len(noisy) - 1)
        noisy = noisy[:cut].rstrip() + "..."
    return noisy


def _random_date(rng: random.Random, config: SynthConfig) -> date:
    offset = rng.randrange(config.num_days)
    return config.start_date + timedelta(days=offset)


def _next_account_ref(rng: random.Random) -> str:
    return f"{TEST_ACCOUNT_PREFIX}{rng.randint(100000, 999999)}"


def _party(rng: random.Random) -> str:
    return rng.choice(_PARTIES)


def generate(config: SynthConfig) -> GeneratedData:
    # Deterministic fake data generation, not a cryptographic use.
    rng = random.Random(config.seed)  # noqa: S311 # nosec B311
    ledger_ids = _IdFactory("LGR")
    bank_ids = _IdFactory("BNK")

    ledger_rows: list[LedgerRow] = []
    bank_rows: list[BankRow] = []
    cases: list[PlantedCase] = []

    # Weighted category choices for "ledger-anchored" cases (slot_cost below
    # is how many ledger transactions the case consumes towards config.count).
    weighted_categories = (
        [Category.NORMAL_EXACT] * 55
        + [Category.NORMAL_DATE_DIFF] * 15
        + [Category.DEPOSIT_IN_TRANSIT] * 4
        + [Category.UNPRESENTED_CHEQUE] * 4
        + [Category.DUPLICATE_SAME_DAY] * 6
        + [Category.ONE_TO_MANY_DEPOSIT] * 6
        + [Category.ERROR_TRANSPOSED_DIGITS] * 3
        + [Category.ERROR_WRONG_AMOUNT] * 3
        + [Category.ERROR_WRONG_DATE] * 4
    )

    slots_used = 0
    while slots_used < config.count:
        category = rng.choice(weighted_categories)
        account_ref = _next_account_ref(rng)

        if category == Category.NORMAL_EXACT:
            txn_date = _random_date(rng, config)
            amount = _random_amount(rng)
            party = _party(rng)
            lid = ledger_ids.next()
            bid = bank_ids.next()
            ledger_rows.append(
                LedgerRow(
                    lid,
                    txn_date,
                    _add_noise(rng, f"{rng.choice(_NORMAL_PHRASES)} - {party}"),
                    amount,
                    account_ref,
                )
            )
            bank_rows.append(
                BankRow(
                    bid,
                    txn_date,
                    _add_noise(rng, f"{rng.choice(_NORMAL_PHRASES)} - {party}"),
                    None,
                    amount,
                    account_ref,
                )
                if amount >= 0
                else BankRow(
                    bid,
                    txn_date,
                    _add_noise(rng, f"{rng.choice(_NORMAL_PHRASES)} - {party}"),
                    -amount,
                    None,
                    account_ref,
                )
            )
            cases.append(PlantedCase(category, [lid], [bid], "exact one-to-one match"))
            slots_used += 1

        elif category == Category.NORMAL_DATE_DIFF:
            ledger_date = _random_date(rng, config)
            bank_date = ledger_date + timedelta(days=rng.randint(1, 5))
            amount = _random_amount(rng)
            party = _party(rng)
            lid = ledger_ids.next()
            bid = bank_ids.next()
            desc = f"{rng.choice(_NORMAL_PHRASES)} - {party}"
            ledger_rows.append(
                LedgerRow(lid, ledger_date, _add_noise(rng, desc), amount, account_ref)
            )
            bank_rows.append(
                BankRow(bid, bank_date, _add_noise(rng, desc), None, amount, account_ref)
                if amount >= 0
                else BankRow(bid, bank_date, _add_noise(rng, desc), -amount, None, account_ref)
            )
            cases.append(
                PlantedCase(category, [lid], [bid], "matches but bank date lags ledger date")
            )
            slots_used += 1

        elif category == Category.DEPOSIT_IN_TRANSIT:
            txn_date = _random_date(rng, config)
            amount = _random_amount(rng)
            party = _party(rng)
            lid = ledger_ids.next()
            ledger_rows.append(
                LedgerRow(lid, txn_date, _add_noise(rng, f"Mədaxil - {party}"), amount, account_ref)
            )
            cases.append(
                PlantedCase(
                    category,
                    [lid],
                    [],
                    "deposit in transit: recorded in ledger, not yet on bank statement",
                )
            )
            slots_used += 1

        elif category == Category.UNPRESENTED_CHEQUE:
            txn_date = _random_date(rng, config)
            amount = -_random_amount(rng)
            party = _party(rng)
            lid = ledger_ids.next()
            ledger_rows.append(
                LedgerRow(
                    lid, txn_date, _add_noise(rng, f"Çek ödənişi - {party}"), amount, account_ref
                )
            )
            cases.append(
                PlantedCase(
                    category,
                    [lid],
                    [],
                    "unpresented cheque: recorded in ledger, not yet cleared by bank",
                )
            )
            slots_used += 1

        elif category == Category.DUPLICATE_SAME_DAY:
            txn_date = _random_date(rng, config)
            amount = _random_amount(rng)
            party_a, party_b = _party(rng), _party(rng)
            lid_a, lid_b = ledger_ids.next(), ledger_ids.next()
            bid_a, bid_b = bank_ids.next(), bank_ids.next()
            ledger_rows.append(
                LedgerRow(
                    lid_a, txn_date, _add_noise(rng, f"Ödəniş - {party_a}"), amount, account_ref
                )
            )
            ledger_rows.append(
                LedgerRow(
                    lid_b, txn_date, _add_noise(rng, f"Ödəniş - {party_b}"), amount, account_ref
                )
            )
            bank_rows.append(
                BankRow(
                    bid_a,
                    txn_date,
                    _add_noise(rng, f"Ödəniş - {party_a}"),
                    None,
                    amount,
                    account_ref,
                )
            )
            bank_rows.append(
                BankRow(
                    bid_b,
                    txn_date,
                    _add_noise(rng, f"Ödəniş - {party_b}"),
                    None,
                    amount,
                    account_ref,
                )
            )
            cases.append(
                PlantedCase(
                    category,
                    [lid_a, lid_b],
                    [bid_a, bid_b],
                    "identical amounts, same day: pair a<->a, b<->b by id order, not swapped",
                )
            )
            slots_used += 2

        elif category == Category.ONE_TO_MANY_DEPOSIT:
            n_legs = rng.randint(2, 4)
            base_date = _random_date(rng, config)
            leg_amounts = [_random_amount(rng, "10.00", "500.00") for _ in range(n_legs)]
            total = round_money(sum(leg_amounts, Decimal("0")))
            lids = []
            for leg_amount in leg_amounts:
                lid = ledger_ids.next()
                lids.append(lid)
                leg_date = base_date - timedelta(days=rng.randint(0, 2))
                ledger_rows.append(
                    LedgerRow(
                        lid,
                        leg_date,
                        _add_noise(rng, f"Mədaxil - {_party(rng)}"),
                        leg_amount,
                        account_ref,
                    )
                )
            bid = bank_ids.next()
            bank_rows.append(BankRow(bid, base_date, "Toplu mədaxil", None, total, account_ref))
            cases.append(
                PlantedCase(
                    category, lids, [bid], f"{n_legs} ledger receipts sum to one bank deposit"
                )
            )
            slots_used += n_legs

        elif category == Category.ERROR_TRANSPOSED_DIGITS:
            txn_date = _random_date(rng, config)
            ledger_amount = _random_amount(rng, "100.00", "9000.00")
            bank_amount = _transpose_digits(rng, ledger_amount)
            party = _party(rng)
            lid = ledger_ids.next()
            bid = bank_ids.next()
            desc = f"Ödəniş - {party}"
            ledger_rows.append(
                LedgerRow(lid, txn_date, _add_noise(rng, desc), ledger_amount, account_ref)
            )
            bank_rows.append(
                BankRow(bid, txn_date, _add_noise(rng, desc), None, bank_amount, account_ref)
            )
            cases.append(
                PlantedCase(
                    category,
                    [lid],
                    [bid],
                    f"transposed-digit error: ledger {ledger_amount} vs bank {bank_amount}",
                )
            )
            slots_used += 1

        elif category == Category.ERROR_WRONG_AMOUNT:
            txn_date = _random_date(rng, config)
            ledger_amount = _random_amount(rng)
            bank_amount = _random_amount(rng)
            party = _party(rng)
            lid = ledger_ids.next()
            bid = bank_ids.next()
            desc = f"Ödəniş - {party}"
            ledger_rows.append(
                LedgerRow(lid, txn_date, _add_noise(rng, desc), ledger_amount, account_ref)
            )
            bank_rows.append(
                BankRow(bid, txn_date, _add_noise(rng, desc), None, bank_amount, account_ref)
            )
            cases.append(
                PlantedCase(
                    category,
                    [lid],
                    [bid],
                    f"wrong amount error: ledger {ledger_amount} vs bank {bank_amount}",
                )
            )
            slots_used += 1

        elif category == Category.ERROR_WRONG_DATE:
            ledger_date = _random_date(rng, config)
            wrong_offset = rng.choice([-45, -30, 30, 45, 60])
            bank_date = ledger_date + timedelta(days=wrong_offset)
            amount = _random_amount(rng)
            party = _party(rng)
            lid = ledger_ids.next()
            bid = bank_ids.next()
            desc = f"Ödəniş - {party}"
            ledger_rows.append(
                LedgerRow(lid, ledger_date, _add_noise(rng, desc), amount, account_ref)
            )
            bank_rows.append(
                BankRow(bid, bank_date, _add_noise(rng, desc), None, amount, account_ref)
            )
            cases.append(
                PlantedCase(
                    category,
                    [lid],
                    [bid],
                    f"wrong-date error: ledger date {ledger_date} vs bank date {bank_date}",
                )
            )
            slots_used += 1

    # Bank-only extras: charges, interest, direct debits. Roughly 8% of count.
    n_extras = max(3, round(config.count * 0.08))
    for _ in range(n_extras):
        account_ref = _next_account_ref(rng)
        txn_date = _random_date(rng, config)
        roll = rng.random()
        bid = bank_ids.next()
        if roll < 0.5:
            amount = _random_amount(rng, "1.00", "50.00")
            desc = rng.choice(_CHARGE_PHRASES)
            bank_rows.append(
                BankRow(bid, txn_date, _add_noise(rng, desc), amount, None, account_ref)
            )
            cases.append(
                PlantedCase(
                    Category.BANK_CHARGE, [], [bid], "bank charge not yet recorded in ledger"
                )
            )
        elif roll < 0.7:
            amount = _random_amount(rng, "1.00", "30.00")
            desc = rng.choice(_INTEREST_PHRASES)
            bank_rows.append(
                BankRow(bid, txn_date, _add_noise(rng, desc), None, amount, account_ref)
            )
            cases.append(
                PlantedCase(
                    Category.BANK_INTEREST, [], [bid], "bank interest not yet recorded in ledger"
                )
            )
        else:
            amount = _random_amount(rng, "5.00", "300.00")
            desc = rng.choice(_DIRECT_DEBIT_PHRASES)
            bank_rows.append(
                BankRow(bid, txn_date, _add_noise(rng, desc), amount, None, account_ref)
            )
            cases.append(
                PlantedCase(
                    Category.DIRECT_DEBIT, [], [bid], "direct debit not yet recorded in ledger"
                )
            )

    return GeneratedData(ledger_rows=ledger_rows, bank_rows=bank_rows, cases=cases, config=config)
