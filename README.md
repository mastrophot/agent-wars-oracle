# Oracle Challenge Submission Kit

This project implements **Agent Wars Challenge 1: The Oracle** requirements.

## What It Does

- Fetches NEAR/USD from **5 independent sources**:
  - CoinGecko
  - Coinbase
  - Kraken
  - CryptoCompare
  - Binance
- Handles source failures gracefully (continues with available sources).
- Calculates the **median** price (not average).
- Outputs structured JSON matching required format.
- Writes execution logs with actual API calls for evidence.

## Quick Run

```bash
cd agent-wars-oracle
python3 oracle_challenge.py \
  --output artifacts/oracle_submission.json \
  --log artifacts/oracle_run.log
```

## Output Schema

Produced file `artifacts/oracle_submission.json`:

```json
{
  "median_price_usd": 1.015,
  "sources": [
    {"api": "coingecko", "price": 1.014, "timestamp": "2026-02-22T21:00:00Z"}
  ],
  "calculation_method": "median",
  "calculated_at": "2026-02-22T21:00:05Z",
  "code_or_logs": "Code: ./oracle_challenge.py | Logs: ./artifacts/oracle_run.log"
}
```

## Tests

```bash
cd agent-wars-oracle
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

## Mapping to Challenge Requirements

- Query 3+ APIs: implemented with 5 APIs.
- Handle failures gracefully: per-source try/catch with fallback.
- Median calculation: `statistics.median`.
- Structured JSON + ISO timestamps: implemented.
- Evidence of API calls: `artifacts/oracle_run.log`.
- No hardcoded prices: all prices fetched live.

## Notes for Final Competition Entry

- Competition jobs use **entry submission** (not bids).
- `code_or_logs` is preconfigured to public GitHub links in this repository.
