"""Deterministic, tiered transaction matcher.

Runs four tiers in order, each consuming from a shared pool of not-yet-
claimed transactions so nothing is matched twice:

1. EXACT     -- same account, amount, and date.
2. DATE_WINDOW -- same account and amount, date within a configurable window.
3. ONE_TO_MANY -- several nearby ledger amounts summing exactly to one bank
   amount. Always a review suggestion, never auto -- CLAUDE.md requires
   one-to-many matches to be "explicit and flagged," which we read as:
   never silently confirmed, even when the grouping is unambiguous.
4. FUZZY_DISCREPANCY -- same account and (date or amount) plus a similar
   description, but the other side doesn't match exactly. Always a review
   suggestion; an amount or date mismatch is never auto-confirmed.

Tiers 1 and 2 auto-match only when exactly one ledger transaction and one
bank transaction share the grouping key (account, amount). Two or more on
either side is ambiguous -- per CLAUDE.md's matching-integrity rule, that
goes to review with every candidate listed, never a coin flip.

Processing order is always the original input list order (or a sort on
values, never on set/dict iteration) so a run is byte-for-byte
reproducible regardless of PYTHONHASHSEED.
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher

from recwise.importer.models import Transaction
from recwise.matching.models import Match, MatchRun, MatchStatus, MatchTier
from recwise.money import round_money

DEFAULT_DATE_WINDOW_DAYS = 7
DEFAULT_ONE_TO_MANY_LOOKBACK_DAYS = 14
DEFAULT_ONE_TO_MANY_MAX_GROUP_SIZE = 4
DEFAULT_ONE_TO_MANY_MAX_POOL = 12
DEFAULT_FUZZY_LOOKBACK_DAYS = 180
DEFAULT_FUZZY_DESCRIPTION_THRESHOLD = 0.5


@dataclass(frozen=True)
class MatchConfig:
    date_window_days: int = DEFAULT_DATE_WINDOW_DAYS
    one_to_many_lookback_days: int = DEFAULT_ONE_TO_MANY_LOOKBACK_DAYS
    one_to_many_max_group_size: int = DEFAULT_ONE_TO_MANY_MAX_GROUP_SIZE
    one_to_many_max_pool: int = DEFAULT_ONE_TO_MANY_MAX_POOL
    fuzzy_lookback_days: int = DEFAULT_FUZZY_LOOKBACK_DAYS
    fuzzy_description_threshold: float = DEFAULT_FUZZY_DESCRIPTION_THRESHOLD


def match(
    ledger: list[Transaction], bank: list[Transaction], config: MatchConfig | None = None
) -> MatchRun:
    cfg = config if config is not None else MatchConfig()
    claimed_ledger: set[str] = set()
    claimed_bank: set[str] = set()
    matches: list[Match] = []

    matches.extend(_match_by_amount(ledger, bank, claimed_ledger, claimed_bank, cfg))
    matches.extend(_match_one_to_many(ledger, bank, claimed_ledger, claimed_bank, cfg))
    matches.extend(_match_fuzzy(ledger, bank, claimed_ledger, claimed_bank, cfg))

    unmatched_ledger = [t for t in ledger if t.external_id not in claimed_ledger]
    unmatched_bank = [t for t in bank if t.external_id not in claimed_bank]
    return MatchRun(
        matches=matches, unmatched_ledger=unmatched_ledger, unmatched_bank=unmatched_bank
    )


def _date_diff_days(a: date, b: date) -> int:
    return abs((a - b).days)


def _match_by_amount(
    ledger: list[Transaction],
    bank: list[Transaction],
    claimed_ledger: set[str],
    claimed_bank: set[str],
    cfg: MatchConfig,
) -> list[Match]:
    """Tiers EXACT and DATE_WINDOW: group by (account, amount).

    Grouping by amount alone (not date) is deliberately conservative: if
    two or more transactions on either side share an account and amount,
    we treat the whole group as ambiguous rather than trying to pair them
    up by nearest date -- a wrong guess here would be a false positive,
    which the auto tier must never produce.
    """
    ledger_groups: dict[tuple[str, Decimal], list[Transaction]] = defaultdict(list)
    for t in ledger:
        ledger_groups[(t.account_ref, t.amount)].append(t)
    bank_groups: dict[tuple[str, Decimal], list[Transaction]] = defaultdict(list)
    for t in bank:
        bank_groups[(t.account_ref, t.amount)].append(t)

    matches: list[Match] = []
    common_keys = sorted(set(ledger_groups) & set(bank_groups))
    for key in common_keys:
        account_ref, amount = key
        l_group = ledger_groups[key]
        b_group = bank_groups[key]

        if len(l_group) == 1 and len(b_group) == 1:
            ledger_txn, bank_txn = l_group[0], b_group[0]
            diff = _date_diff_days(ledger_txn.txn_date, bank_txn.txn_date)
            if diff == 0:
                matches.append(
                    Match(
                        tier=MatchTier.EXACT,
                        status=MatchStatus.AUTO,
                        ledger_ids=[ledger_txn.external_id],
                        bank_ids=[bank_txn.external_id],
                        confidence=1.0,
                        reason=f"exact amount ({amount}) and date match on account {account_ref}",
                    )
                )
                claimed_ledger.add(ledger_txn.external_id)
                claimed_bank.add(bank_txn.external_id)
            elif diff <= cfg.date_window_days:
                confidence = max(0.5, round(0.95 - 0.05 * diff, 2))
                matches.append(
                    Match(
                        tier=MatchTier.DATE_WINDOW,
                        status=MatchStatus.AUTO,
                        ledger_ids=[ledger_txn.external_id],
                        bank_ids=[bank_txn.external_id],
                        confidence=confidence,
                        reason=(
                            f"amount ({amount}) matches on account {account_ref}; "
                            f"bank date is {diff} day(s) from ledger date"
                        ),
                    )
                )
                claimed_ledger.add(ledger_txn.external_id)
                claimed_bank.add(bank_txn.external_id)
            # else: amount matches but dates are too far apart for this
            # tier; leave both unclaimed for the fuzzy tier or unmatched.
        elif len(l_group) > 1 or len(b_group) > 1:
            l_ids = sorted(t.external_id for t in l_group)
            b_ids = sorted(t.external_id for t in b_group)
            matches.append(
                Match(
                    tier=MatchTier.EXACT,
                    status=MatchStatus.REVIEW,
                    ledger_ids=l_ids,
                    bank_ids=b_ids,
                    confidence=0.5,
                    reason=(
                        f"{len(l_group)} ledger and {len(b_group)} bank transaction(s) share "
                        f"amount {amount} on account {account_ref}; ambiguous, needs manual pairing"
                    ),
                )
            )
            claimed_ledger.update(l_ids)
            claimed_bank.update(b_ids)

    return matches


def _match_one_to_many(
    ledger: list[Transaction],
    bank: list[Transaction],
    claimed_ledger: set[str],
    claimed_bank: set[str],
    cfg: MatchConfig,
) -> list[Match]:
    matches: list[Match] = []
    unclaimed_bank = sorted(
        (t for t in bank if t.external_id not in claimed_bank), key=lambda t: t.external_id
    )

    for b in unclaimed_bank:
        pool = [
            t
            for t in ledger
            if t.external_id not in claimed_ledger
            and t.account_ref == b.account_ref
            and 0 <= (b.txn_date - t.txn_date).days <= cfg.one_to_many_lookback_days
        ]
        pool.sort(key=lambda t: (t.txn_date, t.external_id))
        pool = pool[: cfg.one_to_many_max_pool]

        found_groups: list[tuple[Transaction, ...]] = []
        for size in range(2, cfg.one_to_many_max_group_size + 1):
            for combo in itertools.combinations(pool, size):
                if round_money(sum((t.amount for t in combo), Decimal("0"))) == b.amount:
                    found_groups.append(combo)
            if len(found_groups) > 1:
                break

        if len(found_groups) == 1:
            group = found_groups[0]
            l_ids = sorted(t.external_id for t in group)
            matches.append(
                Match(
                    tier=MatchTier.ONE_TO_MANY,
                    status=MatchStatus.REVIEW,
                    ledger_ids=l_ids,
                    bank_ids=[b.external_id],
                    confidence=0.9,
                    reason=(
                        f"{len(group)} ledger transactions sum exactly "
                        f"to this bank amount ({b.amount})"
                    ),
                )
            )
            claimed_ledger.update(l_ids)
            claimed_bank.add(b.external_id)
        elif len(found_groups) > 1:
            all_ids = sorted({t.external_id for group in found_groups for t in group})
            matches.append(
                Match(
                    tier=MatchTier.ONE_TO_MANY,
                    status=MatchStatus.REVIEW,
                    ledger_ids=all_ids,
                    bank_ids=[b.external_id],
                    confidence=0.4,
                    reason=(
                        f"multiple different groupings of ledger transactions sum to this bank "
                        f"amount ({b.amount}); ambiguous, needs manual grouping"
                    ),
                )
            )
            claimed_ledger.update(all_ids)
            claimed_bank.add(b.external_id)

    return matches


def _description_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _match_fuzzy(
    ledger: list[Transaction],
    bank: list[Transaction],
    claimed_ledger: set[str],
    claimed_bank: set[str],
    cfg: MatchConfig,
) -> list[Match]:
    """Same-account candidates with a similar description but a mismatched
    amount or a date far outside the date-window tier. Always REVIEW:
    nothing here agrees exactly, so nothing here is ever auto-confirmed.
    """
    matches: list[Match] = []
    unclaimed_ledger = sorted(
        (t for t in ledger if t.external_id not in claimed_ledger), key=lambda t: t.external_id
    )

    for ledger_txn in unclaimed_ledger:
        if ledger_txn.external_id in claimed_ledger:
            continue

        candidates = [
            bank_txn
            for bank_txn in bank
            if bank_txn.external_id not in claimed_bank
            and bank_txn.account_ref == ledger_txn.account_ref
            and _date_diff_days(bank_txn.txn_date, ledger_txn.txn_date) <= cfg.fuzzy_lookback_days
            and (bank_txn.txn_date == ledger_txn.txn_date or bank_txn.amount == ledger_txn.amount)
        ]
        scored = [
            (round(_description_similarity(ledger_txn.description, c.description), 3), c)
            for c in candidates
        ]
        scored = [(score, c) for score, c in scored if score >= cfg.fuzzy_description_threshold]
        if not scored:
            continue

        scored.sort(key=lambda item: (-item[0], item[1].external_id))
        best_score, best_candidate = scored[0]

        if best_candidate.amount != ledger_txn.amount:
            reason = (
                f"same date, similar description, amounts differ "
                f"(ledger {ledger_txn.amount} vs bank {best_candidate.amount}); "
                f"possible entry error"
            )
        else:
            reason = (
                f"same amount, similar description, dates differ "
                f"(ledger {ledger_txn.txn_date} vs bank {best_candidate.txn_date}); "
                f"possible date error"
            )

        matches.append(
            Match(
                tier=MatchTier.FUZZY_DISCREPANCY,
                status=MatchStatus.REVIEW,
                ledger_ids=[ledger_txn.external_id],
                bank_ids=[best_candidate.external_id],
                confidence=round(0.3 + 0.3 * best_score, 2),
                reason=reason,
            )
        )
        claimed_ledger.add(ledger_txn.external_id)
        claimed_bank.add(best_candidate.external_id)

    return matches
