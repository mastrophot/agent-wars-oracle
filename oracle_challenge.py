#!/usr/bin/env python3
"""Oracle challenge: fetch NEAR/USD from independent sources and compute median."""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    parser: Callable[[Dict[str, Any]], float]


def parse_coingecko(payload: Dict[str, Any]) -> float:
    return float(payload["near"]["usd"])


def parse_coinbase(payload: Dict[str, Any]) -> float:
    return float(payload["data"]["amount"])


def parse_binance(payload: Dict[str, Any]) -> float:
    return float(payload["price"])


def parse_kraken(payload: Dict[str, Any]) -> float:
    if payload.get("error"):
        raise ValueError(f"Kraken returned errors: {payload['error']}")
    result = payload.get("result")
    if not isinstance(result, dict) or not result:
        raise ValueError("Kraken payload missing result")
    first_key = next(iter(result))
    # Kraken ticker field "c" is last closed trade [price, lot volume].
    return float(result[first_key]["c"][0])


def parse_cryptocompare(payload: Dict[str, Any]) -> float:
    return float(payload["USD"])


SOURCES: Tuple[Source, ...] = (
    Source(
        name="coingecko",
        url="https://api.coingecko.com/api/v3/simple/price?ids=near&vs_currencies=usd",
        parser=parse_coingecko,
    ),
    Source(
        name="coinbase",
        url="https://api.coinbase.com/v2/prices/NEAR-USD/spot",
        parser=parse_coinbase,
    ),
    Source(
        name="kraken",
        url="https://api.kraken.com/0/public/Ticker?pair=NEARUSD",
        parser=parse_kraken,
    ),
    Source(
        name="cryptocompare",
        url="https://min-api.cryptocompare.com/data/price?fsym=NEAR&tsyms=USD",
        parser=parse_cryptocompare,
    ),
    Source(
        name="binance",
        url="https://api.binance.com/api/v3/ticker/price?symbol=NEARUSDT",
        parser=parse_binance,
    ),
)


def fetch_json(url: str, timeout_seconds: float) -> Tuple[Dict[str, Any], int, int]:
    req = Request(
        url,
        headers={
            "User-Agent": "near-oracle-challenge/1.0 (+https://market.near.ai)",
            "Accept": "application/json",
        },
    )
    with urlopen(req, timeout=timeout_seconds) as response:
        status_code = int(getattr(response, "status", 200))
        body = response.read()
    payload = json.loads(body.decode("utf-8"))
    return payload, status_code, len(body)


def collect_prices(
    sources: Iterable[Source],
    timeout_seconds: float,
    logger: logging.Logger,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    successes: List[Dict[str, Any]] = []
    failures: List[Dict[str, str]] = []

    for source in sources:
        started = time.monotonic()
        try:
            payload, status_code, byte_count = fetch_json(source.url, timeout_seconds)
            price = source.parser(payload)
            if price <= 0:
                raise ValueError(f"Non-positive price: {price}")
            timestamp = utc_now_iso()
            latency_ms = (time.monotonic() - started) * 1000
            logger.info(
                "api_call_success api=%s status=%s latency_ms=%.2f bytes=%s price=%s url=%s",
                source.name,
                status_code,
                latency_ms,
                byte_count,
                f"{price:.8f}",
                source.url,
            )
            successes.append(
                {
                    "api": source.name,
                    "price": round(float(price), 6),
                    "timestamp": timestamp,
                }
            )
        except (HTTPError, URLError, TimeoutError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            latency_ms = (time.monotonic() - started) * 1000
            logger.warning(
                "api_call_failure api=%s latency_ms=%.2f error=%s url=%s",
                source.name,
                latency_ms,
                repr(exc),
                source.url,
            )
            failures.append({"api": source.name, "error": str(exc)})

    return successes, failures


def build_submission(
    source_points: List[Dict[str, Any]],
    code_or_logs: str,
    min_sources: int,
) -> Dict[str, Any]:
    if len(source_points) < min_sources:
        raise RuntimeError(
            f"Only {len(source_points)} source(s) succeeded. Minimum required: {min_sources}."
        )

    median_price = statistics.median([float(item["price"]) for item in source_points])
    return {
        "median_price_usd": round(float(median_price), 6),
        "sources": source_points,
        "calculation_method": "median",
        "calculated_at": utc_now_iso(),
        "code_or_logs": code_or_logs,
    }


def validate_submission_payload(payload: Dict[str, Any], min_sources: int) -> None:
    required_top_level = {
        "median_price_usd",
        "sources",
        "calculation_method",
        "calculated_at",
        "code_or_logs",
    }
    missing = required_top_level - set(payload)
    if missing:
        raise ValueError(f"Submission missing required top-level fields: {sorted(missing)}")

    if payload["calculation_method"] != "median":
        raise ValueError("calculation_method must be 'median'")

    sources = payload["sources"]
    if not isinstance(sources, list) or len(sources) < min_sources:
        raise ValueError(f"sources must contain at least {min_sources} entries")

    seen_apis = set()
    for item in sources:
        if not isinstance(item, dict):
            raise ValueError("Each source entry must be an object")
        for key in ("api", "price", "timestamp"):
            if key not in item:
                raise ValueError(f"Source entry missing key: {key}")
        api_name = str(item["api"])
        if api_name in seen_apis:
            raise ValueError(f"Duplicate API source found: {api_name}")
        seen_apis.add(api_name)
        if float(item["price"]) <= 0:
            raise ValueError(f"Invalid non-positive price for source: {api_name}")
        # Strict UTC format expected by the challenge examples.
        if not str(item["timestamp"]).endswith("Z"):
            raise ValueError(f"Timestamp must be UTC ISO string ending with 'Z': {api_name}")


def configure_logger(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("oracle_challenge")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)sZ %(levelname)s %(message)s", "%Y-%m-%dT%H:%M:%S")
    formatter.converter = time.gmtime

    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    default_code = (
        "Code: https://github.com/mastrophot/agent-wars-oracle/blob/main/oracle_challenge.py"
        " | Logs: https://github.com/mastrophot/agent-wars-oracle/blob/main/artifacts/oracle_run.log"
    )
    parser = argparse.ArgumentParser(
        description="Fetch NEAR/USD from multiple APIs and produce Oracle challenge submission JSON."
    )
    parser.add_argument(
        "--output",
        default="artifacts/oracle_submission.json",
        help="Output JSON path.",
    )
    parser.add_argument(
        "--log",
        default="artifacts/oracle_run.log",
        help="Execution log path with proof of API calls.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=12.0,
        help="HTTP timeout per API request in seconds.",
    )
    parser.add_argument(
        "--min-sources",
        type=int,
        default=3,
        help="Minimum successful sources required for valid output.",
    )
    parser.add_argument(
        "--code-or-logs",
        default=default_code,
        help="Value for submission field code_or_logs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.output)
    log_path = Path(args.log)

    logger = configure_logger(log_path)
    logger.info("oracle_run_started source_count=%s timeout=%s", len(SOURCES), args.timeout)

    try:
        successes, failures = collect_prices(SOURCES, args.timeout, logger)
        logger.info(
            "oracle_collection_finished success=%s failed=%s",
            len(successes),
            len(failures),
        )

        submission = build_submission(successes, args.code_or_logs, args.min_sources)
        validate_submission_payload(submission, args.min_sources)
        write_json(output_path, submission)

        logger.info(
            "oracle_submission_written output=%s median_price_usd=%s successful_sources=%s",
            output_path,
            submission["median_price_usd"],
            len(successes),
        )

        print(json.dumps(submission, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        logger.exception("oracle_run_failed error=%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
