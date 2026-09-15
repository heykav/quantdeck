"""Data feeds. Import concrete feeds directly from their module, e.g.
``from quantdeck.data.yfinance_feed import YFinanceFeed`` — this keeps
importing ``quantdeck.data.base`` (used for type hints) from requiring
``yfinance``/``pandas`` to be installed.
"""
