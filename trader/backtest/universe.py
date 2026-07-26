"""The frozen D-04 universe lists for Phase 3's strategy sweeps.

Every symbol list below is committed verbatim from 03-RESEARCH.md's Universe
section (Claude's verified live yfinance/ccxt lookups, 2026-07-26) -- not
re-derived here. This module is one of the three frozen_config.FROZEN_FILES
entries: any byte-level edit after FROZEN_HASH is locked (see
trader/backtest/frozen_config.py) is detected by verify_frozen() and blocks
every downstream sweep/OOS entrypoint.

BUCKET_* constants are sweep/regime GROUPING labels, distinct from
trader/backtest/config.py's per-symbol asset_class values ("stock",
"crypto_major", "memecoin") and the instruments table's asset_class CHECK
constraint. A bucket groups symbols for regime/sweep purposes only -- it is
never passed to fills.py or written to the ledger's asset_class column.
"""

from __future__ import annotations

BUCKET_STOCK = "stock"
BUCKET_CRYPTO_MAJOR_LEGACY_MEME = "crypto_major_legacy_meme"
BUCKET_NEW_MEMECOIN = "new_memecoin"

# D-04's 18-symbol stock universe: sanity trio (AAPL, MSFT, GOOGL) plus 15
# additional names spanning high-beta growth/tech and steadier large-caps
# for regime diversity (03-RESEARCH.md Universe > Stocks table).
STOCK_UNIVERSE = [
    "AAPL", "MSFT", "GOOGL",
    "NVDA", "AMD", "TSLA", "AMZN", "META", "NFLX", "CRM", "ADBE",
    "COST", "JPM", "XOM", "UNH", "WMT", "HD", "DIS",
]

# D-04's crypto-major + legacy-memecoin bucket: BTC/ETH (crypto_major
# per-symbol asset_class) plus DOGE/SHIB (memecoin per-symbol asset_class,
# but old enough for the same trending/bear regime pair as BTC/ETH).
CRYPTO_MAJOR_LEGACY_MEME_UNIVERSE = ["BTC/USDT", "ETH/USDT", "DOGE/USDT", "SHIB/USDT"]

# D-04's new-memecoin bucket: PEPE/BONK/WIF, each now (2026-07-26) old enough
# for their own mania/correction regime pair (03-RESEARCH.md's Assumption
# A6 / State of the Art correction to the phase document's original framing).
NEW_MEMECOIN_UNIVERSE = ["PEPE/USDT", "BONK/USDT", "WIF/USDT"]

UNIVERSE_BY_BUCKET: dict[str, list[str]] = {
    BUCKET_STOCK: STOCK_UNIVERSE,
    BUCKET_CRYPTO_MAJOR_LEGACY_MEME: CRYPTO_MAJOR_LEGACY_MEME_UNIVERSE,
    BUCKET_NEW_MEMECOIN: NEW_MEMECOIN_UNIVERSE,
}
