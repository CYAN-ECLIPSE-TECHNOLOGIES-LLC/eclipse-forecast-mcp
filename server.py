#!/usr/bin/env python3
"""Eclipse Forecast MCP — v0.1.0, phase M0 (Polymarket data
adapter, Wing B).

Powered by Cyan Eclipse Technologies (cetech.ai).

Descriptor (mandatory with the name, spec section 12.1):
Eclipse Forecast — the Polymarket adapter: the VENUE'S prices,
with their criteria and liquidity attached. The forecast is the
venue's priced output, never Cyan Eclipse's prediction.

Posture (spec section 4.2): Polymarket Global = Grade C (data)
+ Grade X (US trading). This adapter is READ-ONLY over public
data shapes: Gamma for discovery + criteria text, CLOB public
for books/prices. The US trading surface is ABSENT — there is
no order, trade, account, or API-key tool for a geoblocked
route to land on (spec 8.2: circumvention is a named refusal,
and here it is an absent capability). Polymarket US (QCX) is a
separate venue and a later phase; its data never blends with
Global's in one Quote.

TRANSPORT SEAM (M0 fixture form, stated plainly): venue reads
run against fixtures shaped like the real Gamma / CLOB public
API responses, loaded behind load_fixtures(). The live public-
read transport drops in behind the same seam at a later
verification step; it is labeled not_tested in the manifest.
No network calls exist in this build.

Every output carries money_class: REAL (Polymarket data is
real-money venue data — the label travels even though this
adapter moves no money).

Core seam: instruments, books, quotes, and resolutions are
normalized through Eclipse Book's book_engine against the
SHARED suite state ($ECLIPSE_BOOK_STATE or the Book core's
data/state.json), loaded fresh at every call.

M0 SCOPE: fixtures only. No accounts, no keys, no orders, no
certification claimed — bench pending.

Transport: MCP over stdio, stdlib only.
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).parent
CORE_DIR = HERE.parent / "eclipse-book-mcp"
sys.path.insert(0, str(CORE_DIR))

import book_engine as eng  # noqa: E402
from book_engine import ToolError  # noqa: E402

VENUE = "polymarket_global"
MONEY_CLASS = "REAL"

# Gamma native status vocabulary -> core lifecycle. Anything
# outside this map surfaces as UNMAPPED with the native string
# preserved (spec 5.2), never coerced.
GAMMA_STATUS_MAP = {"active": "OPEN", "closed": "CLOSED"}


def fixture_dir() -> Path:
    return Path(os.environ.get(
        "ECLIPSE_FORECAST_FIXTURES", HERE / "fixtures"))


def load_fixtures(set_name="base") -> dict:
    d = fixture_dir()
    gamma_file = "gamma_markets.json" if set_name == "base" \
        else f"gamma_markets_{set_name}.json"
    out = {"markets": json.loads((d / gamma_file).read_text())["markets"],
           "books": json.loads((d / "clob_books.json").read_text())["books"],
           "resolutions": json.loads(
               (d / "resolutions.json").read_text())["resolutions"]}
    return out


def core_state_path() -> Path:
    return Path(os.environ.get(
        "ECLIPSE_BOOK_STATE", CORE_DIR / "data" / "state.json"))


def load_core_state() -> dict:
    path = core_state_path()
    if path.exists():
        return json.loads(path.read_text())
    state = eng.empty_state()
    seed = json.loads((CORE_DIR / "fixtures.json").read_text())
    eng.ensure_seeded(state, seed)
    save_core_state(state)
    return state


def save_core_state(state: dict) -> None:
    path = core_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=1))


# ------------------------------------------------------------- translation
def _json_list(value):
    if isinstance(value, list):
        return value
    return json.loads(value)


def gamma_native_status(native: dict) -> str:
    if native.get("closed"):
        return "closed"
    if native.get("active"):
        return "active"
    return "unknown"


def parse_gamma_market(native: dict) -> dict:
    """Gamma market -> canonical Instrument spec (core engine
    input). Token-id <-> outcome mapping is pinned from the
    venue's own arrays, never inferred from price (spec 12.1)."""
    outcomes = _json_list(native["outcomes"])
    token_ids = _json_list(native["clobTokenIds"])
    status = gamma_native_status(native)
    return {
        "venue": VENUE, "native_id": native["conditionId"],
        "native_symbol": native.get("slug"),
        "kind": "EVENT_CONTRACT", "title": native["question"],
        "underlying": native.get("groupItemTitle"),
        "outcomes": outcomes,
        "token_ids": token_ids,
        "resolution_criteria": {
            "text": native["description"],
            "source_ref": f"gamma:{native['conditionId']}"},
        "resolution_source": native.get("resolutionSource"),
        "trading_window": {"open": native.get("startDate"),
                           "close": native.get("endDate")},
        "tick": native.get("tickSize", "0.01"), "min_size": "1",
        "currency": "USD", "money_class": MONEY_CLASS,
        "native_status": status,
        "status_mapped": GAMMA_STATUS_MAP.get(status),
        "provenance": {"feed": "gamma-fixture",
                       "fetched_at": "2026-10-25T12:00:00Z",
                       "data_rights": {
                           "source": "Polymarket Gamma public API "
                                     "(fixture-shaped in M0)",
                           "basis": "account-holder + editorial "
                                    "consumption, no redistribution "
                                    "(spec 6)",
                           "method": "fixture file behind the "
                                     "transport seam",
                           "retention": "operational snapshots; "
                                        "own ledger permanent"}}}


def parse_clob_book(native_book: dict, instrument_id: str,
                    outcome: str) -> dict:
    """CLOB book -> canonical Book via the core builder (the
    same builder Strike uses — normalization parity lives in
    the core, spec 5.2)."""
    return eng.build_book(
        instrument_id, VENUE, "CLOB", native_book.get("bids", []),
        native_book.get("asks", []), native_book["timestamp"],
        tick=native_book.get("tick_size", "0.01"),
        native_ref=native_book.get("hash"))


# ------------------------------------------------------------------- tools
def _sync(state, set_name):
    done = state.setdefault("adapter_syncs", {}).setdefault(
        "forecast", [])
    if set_name in done:
        return {"synced": [], "count": 0, "already_synced": True,
                "criteria_changed_events": [],
                "money_class": MONEY_CLASS}
    fx = load_fixtures(set_name)
    synced, events = [], []
    books = fx["books"]
    for native in fx["markets"]:
        spec_in = parse_gamma_market(native)
        result = eng.ingest_instrument(state, spec_in)
        inst = result["instrument"]
        if result["criteria_changed"]:
            events.append(result["criteria_changed"])
        outcomes = spec_in["outcomes"]
        token_ids = spec_in["token_ids"]
        for outcome, token in zip(outcomes, token_ids):
            native_book = books.get(token)
            if native_book is None:
                continue
            book = parse_clob_book(native_book,
                                   inst["instrument_id"], outcome)
            book["outcome"] = outcome
            eng.ingest_book(state, book)
        synced.append(inst["instrument_id"])
    for res in fx["resolutions"]:
        iid = eng.instrument_id_for(VENUE, "EVENT_CONTRACT",
                                    res["condition_id"])
        if iid in state["instruments"]:
            eng.resolution_report(state, {
                "instrument_id": iid, "outcome": res["outcome"],
                "source": res.get("source"),
                "evidence_ref": res.get("evidence_ref"),
                "disputed": res.get("disputed", False)})
    done.append(set_name)
    return {"synced": synced, "count": len(synced),
            "criteria_changed_events": events,
            "money_class": MONEY_CLASS}


def t_forecast_sync(state, args):
    return _sync(state, args.get("fixture_set", "base"))


def t_market_list(state, args):
    _sync(state, "base")
    out = [{"instrument_id": i["instrument_id"], "title": i["title"],
            "status": i["status"], "native_status": i["native_status"],
            "money_class": i["money_class"],
            "resolution_source": i["resolution_source"]}
           for i in state["instruments"].values()
           if i["venue"] == VENUE]
    return {"markets": out, "count": len(out),
            "money_class": MONEY_CLASS}


def t_market_get(state, args):
    _sync(state, "base")
    inst = state["instruments"].get(args["instrument_id"])
    if inst is None or inst["venue"] != VENUE:
        raise ToolError(f"MARKET_NOT_FOUND: {args['instrument_id']}")
    return {"market": eng.guard_no_probability(inst),
            "money_class": MONEY_CLASS}


def t_book_get(state, args):
    _sync(state, "base")
    book = eng.get_book(state, args["instrument_id"],
                        args.get("outcome", "Yes"))
    return {"book": book, "money_class": MONEY_CLASS}


def t_quote_get(state, args):
    _sync(state, "base")
    quote = eng.quote_get(state, args["instrument_id"], args["size"],
                          outcome=args.get("outcome", "Yes"),
                          as_of=args.get("as_of"))
    return {"quote": quote, "money_class": MONEY_CLASS}


def t_resolution_get(state, args):
    _sync(state, "base")
    inst = state["instruments"].get(args["instrument_id"])
    if inst is None or inst["venue"] != VENUE:
        raise ToolError(f"MARKET_NOT_FOUND: {args['instrument_id']}")
    return {"resolution": eng.resolution_view(inst),
            "money_class": MONEY_CLASS}


def t_venue_status(state, args):
    _sync(state, "base")
    status = eng.venue_status(state, VENUE, as_of=args.get("as_of"))
    status["transport"] = "fixtures (Gamma/CLOB-shaped); live " \
                          "public reads not_tested in M0"
    status["us_trading_surface"] = "ABSENT"
    return status


def t_receipt_list(state, args):
    limit = args.get("limit")
    receipts = state["receipts"]
    if limit is not None:
        receipts = receipts[-int(limit):]
    return {"receipts": receipts, "count": len(state["receipts"]),
            "chain_valid": eng.verify_receipt_chain(state["receipts"]),
            "money_class": MONEY_CLASS}


TOOLS = {
    "forecast_sync": (
        t_forecast_sync,
        "T0/T1. Sync the fixture set (base | edited) through "
        "the transport seam into the shared Book core state: "
        "Gamma-shaped markets -> canonical Instruments (criteria "
        "verbatim + hash-pinned), CLOB-shaped books -> canonical "
        "Books, UMA-shaped resolutions -> Resolution records. "
        "Returns any CRITERIA_CHANGED events by name.",
        {"fixture_set": {"type": "string"}}, []),
    "market_list": (
        t_market_list,
        "T0. Polymarket Global markets as canonical Instruments "
        "(status + native status + named resolution source). "
        "Data only — no trading surface exists (spec 4.2/8.2).",
        {}, []),
    "market_get": (
        t_market_get,
        "T0. One market with its verbatim resolution criteria, "
        "criteria version history, and resolution state.",
        {"instrument_id": {"type": "string"}}, ["instrument_id"]),
    "book_get": (
        t_book_get,
        "T0. The canonical CLOB Book for one market outcome: "
        "levels, computed spread, depth summary (liquidity "
        "honesty, spec 5.5).",
        {"instrument_id": {"type": "string"},
         "outcome": {"type": "string"}},
        ["instrument_id"]),
    "quote_get": (
        t_quote_get,
        "T0. Core Quote for one outcome at a stated size: price "
        "+ all-in cost (fee truth) + liquidity flag + verbatim "
        "criteria attached. A price, never a probability (5.5).",
        {"instrument_id": {"type": "string"},
         "size": {"type": "string"}, "outcome": {"type": "string"},
         "as_of": {"type": "string"}},
        ["instrument_id", "size"]),
    "resolution_get": (
        t_resolution_get,
        "T0. Resolution record: REPORTED | VERIFIED | DISPUTED "
        "with the named source + evidence ref. Unverified is "
        "data, not fact (spec 5.4).",
        {"instrument_id": {"type": "string"}}, ["instrument_id"]),
    "venue_status": (
        t_venue_status,
        "T0. Adapter health: transport seam state, fee-schedule "
        "freshness, and the standing fact us_trading_surface = "
        "ABSENT.",
        {"as_of": {"type": "string"}}, []),
    "receipt_list": (
        t_receipt_list,
        "T0. The shared suite ledger (hash-chained) as this "
        "adapter sees it.",
        {"limit": {"type": "integer"}}, []),
}

# Capability denylist, stated in code (spec 8.2/12.1): the US
# trading surface is ABSENT. A geoblock-circumvention-shaped
# request has no tool to land on.
FORBIDDEN_TOOL_NAMES = {
    "place_order", "post_order", "create_order", "order_place",
    "buy", "sell", "trade", "create_api_key", "api_key_create",
    "withdraw", "withdraw_funds", "deposit", "set_allowance",
    "vpn_route", "geo_bypass", "proxy_route", "account_get",
    "balance_get", "positions_get_private",
}


def tool_list():
    return [{"name": name, "description": description,
             "inputSchema": {"type": "object", "properties": props,
                             "required": required}}
            for name, (_, description, props, required) in TOOLS.items()]


def handle(req: dict):
    method, rid = req.get("method", ""), req.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": req.get("params", {}).get(
                "protocolVersion", "2025-03-26"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "eclipse-forecast",
                           "version": "0.1.0"}}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid,
                "result": {"tools": tool_list()}}
    if method == "tools/call":
        name = req["params"]["name"]
        args = req["params"].get("arguments", {})
        if name in FORBIDDEN_TOOL_NAMES or name not in TOOLS:
            return {"jsonrpc": "2.0", "id": rid, "error": {
                "code": -32602,
                "message": f"unknown or line-forbidden tool {name}"}}
        state = load_core_state()
        try:
            out = TOOLS[name][0](state, args)
            save_core_state(state)
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text",
                             "text": json.dumps(out, indent=1)}]}}
        except ToolError as exc:
            save_core_state(state)
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text",
                             "text": json.dumps({"error": str(exc)})}],
                "isError": True}}
    if rid is not None:
        return {"jsonrpc": "2.0", "id": rid, "error": {
            "code": -32601, "message": f"method not found: {method}"}}
    return None


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            response = handle(json.loads(line))
        except Exception as exc:  # never crash the transport
            response = {"jsonrpc": "2.0", "id": None, "error": {
                "code": -32603, "message": str(exc)}}
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
