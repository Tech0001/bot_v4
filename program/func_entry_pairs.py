import asyncio
import random
import time
import json
import logging
from dydx_v4_client.indexer.rest.indexer_client import IndexerClient
from dydx_v4_client.network import TESTNET  # Or replace with MAINNET for production
from constants import DYDX_ADDRESS, ZSCORE_THRESH, USD_PER_TRADE, USD_MIN_COLLATERAL
from func_utils import format_number
from func_cointegration import calculate_zscore
from func_public import get_candles_recent
from func_private import get_open_positions, get_account
from func_bot_agent import BotAgent
import pandas as pd

# Set up logging for better debug tracking
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize IndexerClient for testnet or mainnet
client = IndexerClient(TESTNET.rest_indexer)  # Replace TESTNET with your mainnet if needed

# Define test address (replace with your real address)
test_address = DYDX_ADDRESS

# Refine or remove IGNORE_ASSETS if not necessary
IGNORE_ASSETS = ["", ""]  # Example of assets you want to ignore

# Fetch market data using the correct method
async def fetch_market_data(client, market):
    try:
        # Fetch all perpetual markets and filter for the specific one
        response = await client.getPerpetualMarkets()
        # Filter the specific market you are interested in
        return next((m for m in response["markets"] if m["ticker"] == market), None)
    except Exception as e:
        logger.error(f"Error fetching market data for {market}: {e}")
        return None

# Check if a position is open for a given market
async def is_open_positions(client, market):
    try:
        open_positions = await get_open_positions(client)
        if not isinstance(open_positions, (list, dict)):
            raise ValueError(f"Unexpected data format for open positions: {open_positions}")
        
        return any(position.get("market") == market for position in open_positions)
    except Exception as e:
        logger.error(f"Error checking open positions for {market}: {e}")
        return False

# Place market order
async def place_market_order(client, market, side, size, price, reduce_only):
    try:
        market_data = await fetch_market_data(client, market)
        if not market_data:
            logger.warning(f"Market data for {market} not found. Skipping order.")
            return
        
        order = {
            "market": market,
            "side": side,
            "size": size,
            "price": price,
            "reduce_only": reduce_only
        }
        logger.info(f"Placing order: {order}")
        
        await client.indexer.place_order(order)
    except Exception as e:
        logger.error(f"Error placing market order for {market}: {e}")

# Open positions function - optimized for concurrency
async def open_positions(client):
    # Load cointegrated pairs
    df = pd.read_csv("cointegrated_pairs.csv")
    tasks = []

    # Filter out ignored assets and process the pairs
    for _, row in df.iterrows():
        base_market, quote_market = row["base_market"], row["quote_market"]
        hedge_ratio, half_life = float(row["hedge_ratio"]), row["half_life"]

        if base_market in IGNORE_ASSETS or quote_market in IGNORE_ASSETS:
            logger.info(f"Skipping ignored asset pair: {base_market} - {quote_market}")
            continue

        tasks.append(process_market_pair(client, base_market, quote_market, hedge_ratio, half_life))

    # Execute all market pair tasks concurrently
    await asyncio.gather(*tasks)
    logger.info("All market pairs processed.")

# Helper function to process individual market pairs
async def process_market_pair(client, base_market, quote_market, hedge_ratio, half_life):
    logger.info(f"Processing {base_market} - {quote_market} pair")

    try:
        # Fetch recent prices concurrently for both markets
        series_1, series_2 = await asyncio.gather(
            get_candles_recent(client, base_market),
            get_candles_recent(client, quote_market)
        )
    except Exception as e:
        logger.error(f"Error fetching data for {base_market} or {quote_market}: {e}")
        return

    if series_1 and series_2 and len(series_1) == len(series_2):
        try:
            spread = [float(s1) - (hedge_ratio * float(s2)) for s1, s2 in zip(series_1, series_2)]
            z_score = calculate_zscore(spread).iloc[-1] if isinstance(calculate_zscore(spread), pd.Series) else None

            if z_score is not None and abs(z_score) >= ZSCORE_THRESH:
                await execute_trade(client, base_market, quote_market, z_score, hedge_ratio)
        except Exception as e:
            logger.error(f"Error calculating spread or z-score for {base_market} - {quote_market}: {e}")

# Execute the trade based on z-score
async def execute_trade(client, base_market, quote_market, z_score, hedge_ratio):
    base_side = "BUY" if z_score < 0 else "SELL"
    quote_side = "BUY" if z_score > 0 else "SELL"

    try:
        # Fetch market data for trade execution
        base_market_data, quote_market_data = await asyncio.gather(
            fetch_market_data(client, base_market),
            fetch_market_data(client, quote_market)
        )

        if not base_market_data or not quote_market_data:
            logger.warning(f"Skipping trade. Market data not available for {base_market} or {quote_market}.")
            return

        base_price = float(base_market_data["price"])
        quote_price = float(quote_market_data["price"])
        base_quantity = 1 / base_price * USD_PER_TRADE
        quote_quantity = 1 / quote_price * USD_PER_TRADE

        # Place the orders
        await asyncio.gather(
            place_market_order(client, base_market, base_side, base_quantity, base_price, False),
            place_market_order(client, quote_market, quote_side, quote_quantity, quote_price, False)
        )

        logger.info(f"Trade executed for {base_market} - {quote_market}. Z-Score: {z_score}")
    except Exception as e:
        logger.error(f"Error executing trade for {base_market} - {quote_market}: {e}")

# Main function to fetch account data
async def test_account():
    try:
        response = await client.account.getSubaccounts(test_address)
        subaccounts = response["subaccounts"]
        logger.info(f"Subaccounts: {subaccounts}")
    except Exception as e:
        logger.error(f"Error: {e}")

# Run the account fetch and open positions in parallel
async def main():
    await asyncio.gather(test_account(), open_positions(client))

# Start the asyncio event loop
asyncio.run(main())
