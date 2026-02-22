import unittest

from oracle_challenge import (
    build_submission,
    parse_binance,
    parse_coinbase,
    parse_coingecko,
    parse_cryptocompare,
    parse_kraken,
    validate_submission_payload,
)


class ParseFunctionTests(unittest.TestCase):
    def test_parse_coingecko(self) -> None:
        self.assertEqual(parse_coingecko({"near": {"usd": 1.234}}), 1.234)

    def test_parse_coinbase(self) -> None:
        payload = {"data": {"amount": "1.015", "base": "NEAR", "currency": "USD"}}
        self.assertEqual(parse_coinbase(payload), 1.015)

    def test_parse_binance(self) -> None:
        self.assertEqual(parse_binance({"price": "1.01800000"}), 1.018)

    def test_parse_kraken(self) -> None:
        payload = {
            "error": [],
            "result": {
                "NEARUSD": {
                    "c": ["1.01200", "10.0"],
                }
            },
        }
        self.assertEqual(parse_kraken(payload), 1.012)

    def test_parse_cryptocompare(self) -> None:
        self.assertEqual(parse_cryptocompare({"USD": 1.1001}), 1.1001)


class SubmissionTests(unittest.TestCase):
    def test_build_submission_uses_median(self) -> None:
        sources = [
            {"api": "a", "price": 1.0, "timestamp": "2026-02-22T00:00:00Z"},
            {"api": "b", "price": 3.0, "timestamp": "2026-02-22T00:00:01Z"},
            {"api": "c", "price": 2.0, "timestamp": "2026-02-22T00:00:02Z"},
            {"api": "d", "price": 100.0, "timestamp": "2026-02-22T00:00:03Z"},
        ]
        submission = build_submission(sources, "code+logs", min_sources=3)
        self.assertEqual(submission["median_price_usd"], 2.5)
        self.assertEqual(submission["calculation_method"], "median")
        self.assertEqual(submission["code_or_logs"], "code+logs")

    def test_build_submission_requires_minimum_sources(self) -> None:
        with self.assertRaises(RuntimeError):
            build_submission(
                [{"api": "a", "price": 1.0, "timestamp": "2026-02-22T00:00:00Z"}],
                "x",
                min_sources=3,
            )

    def test_validate_submission_rejects_duplicate_source(self) -> None:
        payload = {
            "median_price_usd": 1.0,
            "sources": [
                {"api": "coingecko", "price": 1.0, "timestamp": "2026-02-22T00:00:00Z"},
                {"api": "coingecko", "price": 1.1, "timestamp": "2026-02-22T00:00:01Z"},
                {"api": "binance", "price": 1.2, "timestamp": "2026-02-22T00:00:02Z"},
            ],
            "calculation_method": "median",
            "calculated_at": "2026-02-22T00:00:05Z",
            "code_or_logs": "logs",
        }
        with self.assertRaises(ValueError):
            validate_submission_payload(payload, min_sources=3)


if __name__ == "__main__":
    unittest.main()
