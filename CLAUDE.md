# CLAUDE.md

## Project
**Recwise (by Esperance).** Source-available (PolyForm Internal Use License 1.0.0), offline bank reconciliation tool (Python). Imports a bank statement and a ledger (CSV/Excel), matches transactions in tiers, lets a human review, and outputs a reconciliation statement. An audit analytics module comes later and reuses the same importer.

Users are accountants. A wrong result is worse than a missing result. Optimize for **correctness and trust**, not cleverness.

## Hard rules (never break these, ask me first if you think one must be bent)

### Money
- Never use `float` for money. Use `decimal.Decimal` everywhere.
- Never let pandas infer amount columns. Read with `dtype=str`, then convert to `Decimal` from the string.
- Set rounding explicitly (`ROUND_HALF_UP`, 2 places) in one helper function. Do not scatter `round()` calls.
- Handle decimal commas ("1.234,56") and thousands separators in the parser, with tests.
- The sign convention (bank credit = ledger debit) is defined in exactly one place and documented there. Do not re-derive it elsewhere.

### Privacy and data
- The tool must work fully offline. No network calls, no telemetry, no analytics, no update checks. If a dependency phones home, do not add it.
- Never commit real financial data. Only synthetic data lives in `sample_data/`. Do not create, paste or invent realistic-looking real account numbers, IBANs or names.
- Never log transaction descriptions, amounts, names or account numbers. Logs may contain counts, IDs, timings and error types only. This applies to every output stream, not just the audit log — analytics reports, future exports, and anything else derived from transaction data must not surface raw descriptions or amounts outside the reconciliation/export outputs the user directly requested.
- Treat all input files as untrusted: cap file size, validate columns and types, fail with a clear error instead of guessing.

### Security
- Never use `eval`, `exec`, `pickle`, `yaml.load` (use `safe_load`), `shell=True`, or `os.system`.
- CSV/Excel export must neutralize formula injection: any cell starting with `=`, `+`, `-`, `@`, tab or carriage return gets prefixed with `'`. Write a shared `sanitize_cell()` and test it. Negative numbers stay numeric, only text cells get sanitized.
- Never build file paths from user input without resolving and checking they stay inside the intended directory.
- Read input files read-only. Never modify or overwrite the user's originals.
- No secrets, tokens or credentials in code, tests or config. If the UI runs a local server, bind to `127.0.0.1` only.
- Every state-changing web route (anything that writes review decisions, matches, or exports) must check a per-process CSRF token before acting. Never use Jinja's `|safe`, `Markup`, or `render_template_string` on anything that could contain untrusted content — rely on autoescaping.
- Do not add a dependency without asking. When you propose one, say what it does, why stdlib is not enough, and whether it is maintained. Pin versions. Also state its license, and do not add GPL or AGPL dependencies without asking me, because they could conflict with this project's license terms.

### Matching integrity
- One-to-one by default: a transaction can be matched only once. One-to-many matches must be explicit and flagged.
- Auto-match only above a confidence threshold. Anything ambiguous (for example two identical payments on the same day) goes to human review, never a coin flip.
- Every match stores: tier, confidence, and a plain-English reason.
- Matching must be deterministic: same input, same output, no dependence on row order or random seeds.
- Never auto-post journals. Suggest only.
- Write an audit log entry for every match, unmatch and manual decision.

## Code standards
- Python 3.11+, type hints on all functions, `mypy --strict` clean.
- Format and lint with `ruff`. Security scan with `bandit`. Dependency check with `pip-audit`.
- Small pure functions. Keep parsing, matching, and output in separate modules. No business logic in the UI layer.
- Use dataclasses or pydantic models for transactions and matches, not loose dicts.
- Handle encoding explicitly: UTF-8 with BOM support, and test Azerbaijani characters (ə, ı, ş, ç, ö, ü, ğ) in descriptions.
- Errors: raise specific exceptions with helpful messages. No bare `except`, no silently swallowed errors.
- Comments explain *why*, not *what*. Accounting rules get a comment naming the rule.

## Testing
- Every function gets tests. Bug fix = add a failing test first, then fix.
- Use `pytest`. Use `hypothesis` for parsers and money maths where useful.
- The synthetic data generator uses a fixed seed and produces an **answer key**. Planted cases include: timing differences, duplicate amounts, bank charges, one-to-many deposits, wrong dates, and messy formats.
- Report precision and recall against the answer key. **False positives in the auto-match tier must be zero.** If a change raises recall by adding false positives, reject it.
- Tests must never depend on real data or the network.

## Workflow
- For anything touching more than one file, write a short plan first and wait for my OK.
- Small commits, one concern each, with clear messages.
- Before saying a task is done, actually run: `pytest`, `ruff check`, `mypy`, `bandit -r src`. Report the real results. Do not claim tests pass without running them.
- If an accounting rule is unclear, ask me. Do not guess how a treatment works.
- If you are unsure or a request conflicts with this file, say so instead of quietly picking one.
- Do not refactor unrelated code, rename things, or "improve" files outside the current task.

## Definition of done (v1)
On a synthetic dataset of ~1,000 transactions with planted issues: high auto-match rate, zero false positives in the auto tier, a correct reconciliation statement (balance per bank ± items = balance per cash book), suggested journals for unrecorded items, and a sanitized export.

## Out of scope for v1
PDF statement parsing, bank APIs, multi-currency, user accounts, cloud anything.
