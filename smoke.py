#!/usr/bin/env python3
"""End-to-end stdio smoke for Eclipse Forecast v0.1 (M0).

Temp shared Book state. Drives initialize -> market_list ->
quote_get (thin market: THIN + $200 at best) -> quote_get (Fed:
DEEP + all-in) -> resolution_get (DISPUTED) -> venue_status
(us_trading_surface ABSENT).
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
AS_OF = "2026-10-25T13:00:00Z"


def rpc(proc, rid, method, params=None):
    req = {"jsonrpc": "2.0", "id": rid, "method": method,
           "params": params or {}}
    proc.stdin.write(json.dumps(req) + "\n")
    proc.stdin.flush()
    return json.loads(proc.stdout.readline())


def call(proc, rid, name, args):
    response = rpc(proc, rid, "tools/call",
                   {"name": name, "arguments": args})
    return json.loads(response["result"]["content"][0]["text"])


def main():
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ)
        env["ECLIPSE_BOOK_STATE"] = str(Path(tmp) / "state.json")
        proc = subprocess.Popen(
            [sys.executable, str(HERE / "server.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
            cwd=str(HERE), env=env)
        try:
            init = rpc(proc, 1, "initialize",
                       {"protocolVersion": "2025-03-26"})
            assert init["result"]["serverInfo"]["name"] == \
                "eclipse-forecast"
            print("initialize OK")

            markets = call(proc, 2, "market_list", {})
            assert markets["count"] == 4, markets
            assert markets["money_class"] == "REAL"
            print("market_list OK; 4 fixture markets, money_class REAL")

            thin = call(proc, 3, "quote_get", {
                "instrument_id":
                    "B:polymarket_global:cond-sf-rain-20261101",
                "size": "10", "as_of": AS_OF})["quote"]
            assert thin["liquidity_flag"] == "THIN", thin
            assert thin["depth_summary"]["notional_at_best_ask"] == "200"
            print("quote_get OK; thin market: THIN, $200 at best")

            fed = call(proc, 4, "quote_get", {
                "instrument_id": "B:polymarket_global:cond-fed-dec-2026",
                "size": "100", "as_of": AS_OF})["quote"]
            assert fed["all_in_buy_cost"]["total"] == "62.465", fed
            assert fed["liquidity_flag"] == "DEEP"
            print("quote_get OK; Fed market: DEEP, all-in 62.465")

            res = call(proc, 5, "resolution_get", {
                "instrument_id":
                    "B:polymarket_global:cond-city-ballot-2026"})
            assert res["resolution"]["state"] == "DISPUTED", res
            print("resolution_get OK; ballot market DISPUTED (first-class)")

            status = call(proc, 6, "venue_status", {"as_of": AS_OF})
            assert status["us_trading_surface"] == "ABSENT"
            print("venue_status OK; US trading surface ABSENT")
            print("SMOKE PASSED")
        finally:
            proc.stdin.close()
            proc.terminate()


if __name__ == "__main__":
    main()
