# Eclipse Forecast MCP

**Powered by Cyan Eclipse Technologies** — https://cetech.ai

**Eclipse Forecast — the Polymarket adapter: the venue's prices, with their criteria and liquidity attached.**

The descriptor is the naming law for this adapter (spec §12.1): the forecast is the **venue's priced output, never Cyan Eclipse's prediction**. Every quote that leaves this adapter carries the market's verbatim resolution criteria and its liquidity context in the same object as the price.

## Why this exists

Polymarket's prices are the editorial reference standard for event markets — cited by newsrooms — but a raw price is exactly the part that misleads: it hides the words that will settle the contract, the thinness of the book behind it, and whether a resolution is final or disputed. Forecast normalizes Polymarket Global's public data (Gamma discovery + criteria, CLOB books) through the Eclipse Book core, so consumers — The White Report desk first (spec §15) — get price + criteria + depth + resolution state as one honest record.

## Status — honest labels

v0.1.0, phase **M0 (data adapter)**. Local stdio transport, Python stdlib only. Reads run against **fixtures shaped like the real Gamma / CLOB public API responses**, behind a transport seam (`load_fixtures()`); the live public-read transport is a later verification step and is labeled `not_tested` in the manifest. **No accounts, no keys, no orders, no network calls, and no certification claimed — bench pending.** Own suites: 12/12 tests + stdio smoke passing.

## Posture — data only, and the trading surface is absent

Polymarket Global is Grade C (data) + Grade X (US trading) in the suite spec (§4.2): US persons have been geoblocked from trading since the January 2022 CFTC settlement. This adapter contains **no order, trade, account, deposit, or API-key tool at all** — a geoblock-circumvention-shaped request (`vpn_route`, `geo_bypass`, …) has no tool to land on and is refused by name (`-32602`). Circumvention isn't a disabled feature; it's an absent capability (§8.2). Polymarket US (QCX, the separate CFTC-designated venue) is a later phase with its own chapter — its data never blends with Global's in one Quote.

## What it does

- **Gamma → canonical Instruments**: questions and `description` criteria stored **verbatim + hash-pinned** by the Book core; outcome ↔ token-id mapping pinned from the venue's own arrays, never inferred from price. The shipped fixtures include a market whose criteria the venue later edits — re-syncing the `edited` fixture set produces a named `CRITERIA_CHANGED` event, and positions recorded before the edit keep the entry criteria (proven by test).
- **CLOB → canonical Books + Quotes**: all-in cost from Polymarket's dated fee schedule (fee truth, §5.3); a thin fixture market ($200 at best) flags **THIN**; quote outputs carry `money_class: REAL` — Polymarket data is real-money venue data, and the label travels on every output.
- **UMA resolutions**: fixture resolutions ingest through the core lifecycle; the disputed ballot market sits in the first-class **DISPUTED** state — data, not fact (§5.4).

## Tools (8)

`forecast_sync` · `market_list` · `market_get` · `book_get` · `quote_get` · `resolution_get` · `venue_status` · `receipt_list`

## The probability law applies here most of all

A prediction market's price is a price. No output of this adapter contains a probability field — the Book core guard scans outputs and the adapter's tests re-scan every surface. Editorial consumers may write "the market prices this at…" only with the liquidity context in the same sentence (§15.3); that discipline starts with the objects this adapter emits.

Spec: `~/workspace/cyan-eclipse/eclipse-markets-suite-spec-20261025.md` (§4.2, §12.1). Suite core: Eclipse Book. This is data and tooling, **not financial advice**.

A Cyan Eclipse Technologies product. The "Powered by Cyan Eclipse Technologies" attribution travels with it.
