"""Eclipse Forecast v0.1 tests — Gamma/CLOB fixture translation,
criteria pinning + the edited-criteria flow (spec 5.4/12.1),
THIN liquidity (5.5), DISPUTED resolutions (5.4), fee truth +
staleness (5.3), money_class REAL on every output, probability
law, and the absent US trading surface (denylist)."""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).parent.parent
CORE = HERE.parent / "eclipse-book-mcp"
sys.path.insert(0, str(CORE))
sys.path.insert(0, str(HERE))

import book_engine as eng  # noqa: E402
import server as srv  # noqa: E402

AS_OF = "2026-10-25T13:00:00Z"
FED = "B:polymarket_global:cond-fed-dec-2026"
THIN = "B:polymarket_global:cond-sf-rain-20261101"
DISPUTED = "B:polymarket_global:cond-city-ballot-2026"
EDIT = "B:polymarket_global:cond-btc-120k-20261231"
CRITERIA_V1 = "This market resolves Yes if the BTC-USD daily " \
              "close on Coinbase on December 31, 2026 is at or " \
              "above $120,000. Otherwise it resolves No."


def synced_state():
    state = eng.empty_state()
    seed = __import__("json").loads(
        (CORE / "fixtures.json").read_text())
    eng.ensure_seeded(state, seed)
    srv._sync(state, "base")
    return state


class TestSyncAndMarkets(unittest.TestCase):
    def test_four_markets_money_class_real(self):
        state = synced_state()
        out = srv.t_market_list(state, {})
        self.assertEqual(out["count"], 4)
        self.assertEqual(out["money_class"], "REAL")
        for m in out["markets"]:
            self.assertEqual(m["money_class"], "REAL")

    def test_criteria_verbatim_and_hash_pinned(self):
        state = synced_state()
        market = srv.t_market_get(state, {"instrument_id": EDIT})
        inst = market["market"]
        self.assertEqual(inst["resolution_criteria"], CRITERIA_V1)
        self.assertEqual(inst["criteria_versions"][0]["hash"],
                         eng.sha(CRITERIA_V1))
        self.assertEqual(inst["resolution_source"],
                         "Coinbase BTC-USD daily close")
        self.assertEqual(inst["status"], "OPEN")

    def test_token_outcome_mapping_pinned(self):
        state = synced_state()
        book = srv.t_book_get(state, {"instrument_id": FED,
                                      "outcome": "Yes"})
        self.assertEqual(book["book"]["asks"][0]["price"], "0.62")


class TestQuotes(unittest.TestCase):
    def test_thin_market_flagged_thin(self):
        state = synced_state()
        out = srv.t_quote_get(state, {"instrument_id": THIN,
                                      "size": "10", "as_of": AS_OF})
        q = out["quote"]
        self.assertEqual(q["liquidity_flag"], "THIN")
        self.assertEqual(q["depth_summary"]["notional_at_best_ask"],
                         "200")
        self.assertIn("National Weather Service",
                      q["resolution_criteria"] + q["resolution_source"])
        self.assertEqual(out["money_class"], "REAL")

    def test_deep_market_all_in_and_max_payout(self):
        state = synced_state()
        q = srv.t_quote_get(state, {"instrument_id": FED,
                                    "size": "100",
                                    "as_of": AS_OF})["quote"]
        self.assertEqual(q["liquidity_flag"], "DEEP")
        self.assertEqual(q["fee_status"], "FRESH")
        # 100 x 0.62 = 62 gross; taker 75bps -> 0.465 fee.
        self.assertEqual(q["all_in_buy_cost"]["total"], "62.465")
        self.assertEqual(q["max_payout_for_size"], "100")

    def test_stale_fee_schedule_unverified(self):
        state = synced_state()
        q = srv.t_quote_get(state, {"instrument_id": FED,
                                    "size": "10",
                                    "as_of": "2026-12-25T00:00:00Z"}
                            )["quote"]
        self.assertEqual(q["fee_status"], "STALE")
        self.assertEqual(q["all_in_buy_cost"], "FEE_UNVERIFIED")

    def test_no_probability_fields_anywhere(self):
        state = synced_state()
        outputs = [
            srv.t_market_list(state, {}),
            srv.t_market_get(state, {"instrument_id": FED}),
            srv.t_book_get(state, {"instrument_id": FED,
                                   "outcome": "Yes"}),
            srv.t_quote_get(state, {"instrument_id": FED,
                                    "size": "10", "as_of": AS_OF}),
            srv.t_resolution_get(state, {"instrument_id": DISPUTED}),
            srv.t_venue_status(state, {"as_of": AS_OF})]
        for out in outputs:
            self.assertEqual(eng.probability_scan(out), [])


class TestResolutions(unittest.TestCase):
    def test_disputed_resolution_first_class(self):
        state = synced_state()
        res = srv.t_resolution_get(state,
                                   {"instrument_id": DISPUTED})
        self.assertEqual(res["resolution"]["state"], "DISPUTED")
        self.assertEqual(res["resolution"]["outcome"], "Yes")
        self.assertEqual(res["money_class"], "REAL")


class TestCriteriaEditFlow(unittest.TestCase):
    def test_position_keeps_entry_criteria_after_edit(self):
        state = synced_state()
        pos = eng.position_open(state, {
            "instrument_id": EDIT, "size": "50",
            "entry_price": "0.44", "outcome": "Yes"})["position"]
        out = srv.t_forecast_sync(state, {"fixture_set": "edited"})
        events = out["criteria_changed_events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "CRITERIA_CHANGED")
        self.assertEqual(events[0]["old_hash"], eng.sha(CRITERIA_V1))
        view = eng.position_view(state, state["positions"][
            pos["position_id"]])
        self.assertTrue(view["criteria_changed_since_entry"])
        self.assertEqual(view["criteria_as_of_entry"]["text"],
                         CRITERIA_V1)
        self.assertIn("23:59 UTC", view["criteria_current"]["text"])


class TestDenylist(unittest.TestCase):
    def test_tool_surface_is_exactly_the_data_surface(self):
        self.assertEqual(set(srv.TOOLS), {
            "forecast_sync", "market_list", "market_get", "book_get",
            "quote_get", "resolution_get", "venue_status",
            "receipt_list"})

    def test_trading_and_circumvention_names_refused(self):
        for name in ("place_order", "create_api_key", "vpn_route",
                     "geo_bypass", "withdraw"):
            resp = srv.handle({"method": "tools/call", "id": 1,
                               "params": {"name": name,
                                          "arguments": {}}})
            self.assertEqual(resp["error"]["code"], -32602, name)

    def test_venue_status_states_us_trading_absent(self):
        state = synced_state()
        status = srv.t_venue_status(state, {"as_of": AS_OF})
        self.assertEqual(status["us_trading_surface"], "ABSENT")


if __name__ == "__main__":
    unittest.main()
