"""Live smoke test against the real CoinGecko API — no mocks.

Confirms classify_crypto_instrument's category heuristic against two named
coins: Dogecoin (expected memecoin) and Bitcoin (expected crypto_major).
Mirrors trader/ground_truth/smoke.py's live-verification pattern (D-16,
01-RESEARCH.md).

Run with: .venv\\Scripts\\python.exe -m trader.data.classify_smoke
"""

import os
import sys

from dotenv import load_dotenv

from trader.data.classify import classify_crypto_instrument


def main() -> int:
    load_dotenv()
    api_key = os.environ.get("COINGECKO_API_KEY", "")

    dogecoin_result = classify_crypto_instrument("dogecoin", api_key)
    print(f"dogecoin -> {dogecoin_result}")

    bitcoin_result = classify_crypto_instrument("bitcoin", api_key)
    print(f"bitcoin -> {bitcoin_result}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
