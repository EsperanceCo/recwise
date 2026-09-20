"""Benford's Law first-digit analysis: a standard audit CAAT (computer-
assisted audit technique) for spotting transaction populations that look
fabricated, manually altered, or otherwise unusual.

Naturally occurring amounts (invoices, disbursements, etc.) tend to have
leading digits distributed per Benford's Law -- 1 appears first about 30%
of the time, 9 about 4.6% of the time. A population that deviates sharply
is worth an auditor's attention; it is a screening signal, not proof of
anything on its own.

Conformity thresholds (mean absolute deviation of observed vs. expected
proportion, averaged over the 9 digits) follow Nigrini's widely-used
digit-analysis guidance. Pure stdlib: no new dependency needed for this.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from recwise.importer.models import Transaction

# Below this sample size, first-digit conformity is not considered
# statistically meaningful (Nigrini's guidance for the first-digit test).
MIN_SAMPLE_SIZE = 300

# Nigrini's mean-absolute-deviation conformity thresholds for the
# first-digit test.
_MAD_CLOSE = 0.006
_MAD_ACCEPTABLE = 0.012
_MAD_MARGINAL = 0.015


class Conformity(StrEnum):
    CLOSE = "close_conformity"
    ACCEPTABLE = "acceptable_conformity"
    MARGINAL = "marginally_acceptable"
    NONCONFORMITY = "nonconformity"


def expected_proportions() -> dict[int, float]:
    """Benford's Law expected proportion for each leading digit, 1-9."""
    return {d: math.log10(1 + 1 / d) for d in range(1, 10)}


def leading_digit(amount: Decimal) -> int | None:
    """First significant (non-zero) digit of the amount's magnitude.

    None for a zero amount, which has no leading digit and is excluded
    from the analysis.
    """
    magnitude = abs(amount)
    if magnitude == 0:
        return None
    for ch in format(magnitude, "f"):
        if ch.isdigit() and ch != "0":
            return int(ch)
    return None


@dataclass(frozen=True)
class DigitStat:
    digit: int
    observed_count: int
    observed_proportion: float
    expected_proportion: float

    @property
    def absolute_deviation(self) -> float:
        return abs(self.observed_proportion - self.expected_proportion)


def _classify_mad(mad: float) -> Conformity:
    if mad < _MAD_CLOSE:
        return Conformity.CLOSE
    if mad < _MAD_ACCEPTABLE:
        return Conformity.ACCEPTABLE
    if mad < _MAD_MARGINAL:
        return Conformity.MARGINAL
    return Conformity.NONCONFORMITY


@dataclass(frozen=True)
class BenfordResult:
    sample_size: int
    digit_stats: list[DigitStat]
    mean_absolute_deviation: float
    conformity: Conformity
    sufficient_sample: bool


def analyze(transactions: list[Transaction]) -> BenfordResult:
    """Run the first-digit Benford's Law test over a transaction population.

    Deterministic and pure: same input, same output. Zero-amount
    transactions are excluded (no leading digit); sign is ignored
    (Benford's Law applies to magnitude).
    """
    digit_counts: dict[int, int] = dict.fromkeys(range(1, 10), 0)
    for txn in transactions:
        digit = leading_digit(txn.amount)
        if digit is not None:
            digit_counts[digit] += 1

    sample_size = sum(digit_counts.values())
    expected = expected_proportions()

    if sample_size == 0:
        digit_stats = [DigitStat(d, 0, 0.0, expected[d]) for d in range(1, 10)]
        return BenfordResult(
            sample_size=0,
            digit_stats=digit_stats,
            mean_absolute_deviation=0.0,
            conformity=Conformity.NONCONFORMITY,
            sufficient_sample=False,
        )

    digit_stats = [
        DigitStat(
            digit=d,
            observed_count=digit_counts[d],
            observed_proportion=digit_counts[d] / sample_size,
            expected_proportion=expected[d],
        )
        for d in range(1, 10)
    ]
    mad = sum(stat.absolute_deviation for stat in digit_stats) / 9
    return BenfordResult(
        sample_size=sample_size,
        digit_stats=digit_stats,
        mean_absolute_deviation=mad,
        conformity=_classify_mad(mad),
        sufficient_sample=sample_size >= MIN_SAMPLE_SIZE,
    )
