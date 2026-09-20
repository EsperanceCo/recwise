# Recwise

**Offline bank reconciliation for accountants.** Import a bank statement and a ledger, match them with explainable rules, review the results, and get a reconciliation statement. Audit analytics is planned for later.

> **Status: pre-alpha.** Nothing here is ready to use yet. This README describes what Recwise is being built to do.

## Why

Reconciliation is tedious, easy to get wrong, and every business does it every month. Most tools want your financial data uploaded to a cloud. Recwise is designed to run entirely on your own machine.

## Design principles

- **Local-first:** no network calls, no telemetry, no accounts.
- **Explainable:** every match records its tier, a confidence score, and a plain-English reason.
- **Human in the loop:** nothing is ever posted automatically. A missed match costs a minute; a wrong match hides an error, so uncertain cases go to review.
- **Exact money:** `Decimal` arithmetic only, never floats.
- **Auditable:** every match, unmatch, and manual decision is logged.

## Planned scope (v1)

- [ ] Import bank statement and ledger (CSV/Excel) with column mapping
- [ ] Normalize dates, amounts, and descriptions (including non-ASCII text)
- [ ] Tiered matching: exact, date window, fuzzy description, one-to-many
- [ ] Review screen: accept, reject, or manually match
- [ ] Classify leftovers: timing differences vs items needing a journal
- [ ] Reconciliation statement and suggested journals
- [ ] Export with spreadsheet-formula-injection protection

**Not in v1:** PDF statement parsing, bank APIs, multi-currency, user accounts.

## How it's tested

Recwise is developed against **synthetic data with a known answer key**, so precision and recall can be measured instead of guessed. The auto-match tier must produce zero false positives. No real financial data is ever committed to this repository.

## Disclaimer

Recwise assists with reconciliation. It does not replace professional review, and its output should be checked by a qualified person before use. Provided as-is under the PolyForm Internal Use License 1.0.0.

## About the name

**Recwise:** "rec" is accountants' shorthand for reconciliation.

**Esperance**, the maker: *espérance* is French for hope, and an old English word for it too. The name reflects the goal: hope for a better future. <!-- TODO: add how you pronounce it -->

## License

Recwise is **source-available**, not open source. It is licensed under the [PolyForm Internal Use License 1.0.0](LICENSE): you may use and modify it for the internal business operations of you and your company, but you may not distribute, resell, or sublicense it. For any other use, please contact the author.
