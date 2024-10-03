# Imports
import random
import time
import json
from dydx_v4_client.indexer.rest.constants import TradingRewardAggregationPeriod, OrderType
from dydx_v4_client.indexer.rest.indexer_client import IndexerClient
from dydx_v4_client.network import TESTNET  # For testnet configuration
from constants import DYDX_ADDRESS, ZSCORE_THRESH, USD_PER_TRADE, USD_MIN_COLLATERAL
from func_utils import format_number
from func_cointegration import calculate_zscore
from func_public import get_candles_recent
from func_private import get_open_positions, get_account
from func_bot_agent import BotAgent
import pandas as pd
import asyncio

# Initialize IndexerClient for testnet or mainnet
client = IndexerClient(TESTNET.rest_indexer)  # Replace TESTNET with your mainnet if needed

# Define test address (replace with your real address)
test_address = DYDX_ADDRESS

# Refine or remove IGNORE_ASSETS if not necessary
IGNORE_ASSETS = ["", ""]  # Example of assets you want to ignore

# Check if a position is open for a given market
async def is_open_positions(client, market):
    try:
        open_positions = await get_open_positions(client)

        # Ensure open_positions is a list or dictionary-like structure before processing
        if not isinstance(open_positions, (list, dict)):
            raise ValueError(f"Unexpected data format for open positions: {open_positions}")

        for position in open_positions:
            if isinstance(position, dict) and position.get("market") == market:
                return True
        return False
    except Exception as e:
        print(f"Error checking open positions for {market}: {e}")
        return False

# Place market order (using preexisting functions)
async def place_market_order(client, market, side, size, price, reduce_only):
    try:
        # Fetch market data from IndexerClient (you may need to adjust this to the actual available method)
        market_data = await client.get_markets()  # Fetch available markets data

        # Example structure for order placement
        order = {
            "market": market,
            "side": side,
            "size": size,
            "price": price,
            "reduce_only": reduce_only
        }
        print(f"Placing order: {order}")

        # Call appropriate method for placing order (adjust to your available functions)
        await client.place_order(order)

    except Exception as e:
        print(f"Error placing market order for {market}: {e}")

# Function to open positions (using preexisting methods)
async def open_positions(client):
    # Load cointegrated pairs
    df = pd.read_csv("cointegrated_pairs.csv")

    # Initialize container for BotAgent results
    bot_agents = []

    # Open JSON file and load existing bot agents
    try:
        with open("bot_agents.json") as open_positions_file:
            open_positions_dict = json.load(open_positions_file)
            for p in open_positions_dict:
                bot_agents.append(p)
    except FileNotFoundError:
        bot_agents = []

    # Iterate through cointegrated pairs
    for index, row in df.iterrows():
        base_market = row["base_market"]
        quote_market = row["quote_market"]
        hedge_ratio = float(row["hedge_ratio"])  # Ensure hedge_ratio is converted to float
        half_life = row["half_life"]

        # Skip ignored assets
        if base_market in IGNORE_ASSETS or quote_market in IGNORE_ASSETS:
            print(f"Skipping ignored asset pair: {base_market} - {quote_market}")
            continue

        # Log to ensure BTC-USD is being processed
        if base_market == "BTC-USD" or quote_market == "BTC-USD":
            print(f"Processing BTC-USD pair: {base_market} - {quote_market}")

        # Get recent prices
        try:
            series_1 = await get_candles_recent(client, base_market)
            series_2 = await get_candles_recent(client, quote_market)
        except Exception as e:
            print(f"Error fetching data for {base_market} or {quote_market}: {e}")
            continue

        # Ensure data length is the same and calculate z-score
        if series_1 is not None and series_2 is not None and len(series_1) == len(series_2):
            try:
                spread = [float(s1) - (hedge_ratio * float(s2)) for s1, s2 in zip(series_1, series_2)]

                # Calculate z-score for the last element in the spread
                if len(spread) > 0:
                    z_score = calculate_zscore(spread)
                    if isinstance(z_score, (pd.Series, list)):
                        z_score = z_score.iloc[-1] if isinstance(z_score, pd.Series) else z_score[-1]

                    # Now ensure the z_score is a scalar and compare it to the threshold
                    if abs(z_score) >= ZSCORE_THRESH:
                        # Proceed with trade logic if condition is met
                        is_base_open = await is_open_positions(client, base_market)
                        is_quote_open = await is_open_positions(client, quote_market)

                        if not is_base_open and not is_quote_open:
                            base_side = "BUY" if z_score < 0 else "SELL"
                            quote_side = "BUY" if z_score > 0 else "SELL"

                            # Fetch market data for size and price calculations
                            try:
                                base_market_data = await client.get_markets()  # Correct method
                                quote_market_data = await client.get_markets()  # Correct method
                            except Exception as e:
                                print(f"Error fetching market data for {base_market} or {quote_market}: {e}")
                                continue

                            base_price = series_1[-1]
                            quote_price = series_2[-1]
                            base_quantity = 1 / base_price * USD_PER_TRADE
                            quote_quantity = 1 / quote_price * USD_PER_TRADE

                            # Ensure minimum order size and place the orders
                            await place_market_order(client, base_market, base_side, base_quantity, base_price, False)
                            await place_market_order(client, quote_market, quote_side, quote_quantity, quote_price, False)
    
            except TypeError as te:
                print(f"Error calculating spread or z-score: {te}")

    # Save agents to the file
    print("Success: All open trades checked")

# Main function to fetch account data
async def test_account():
    try:
        response = await client.account.get_subaccounts(test_address)
        subaccounts = response["subaccounts"]
        print(f"Subaccounts: {subaccounts}")
        if subaccounts is None:
            print("Subaccounts is None")
        else:
            print(f"Number of subaccounts: {len(subaccounts)}")
            if len(subaccounts) > 0:
                subaccount0 = subaccounts[0]
                subaccount_number = subaccount0["subaccountNumber"]
                print(f"Subaccount number: {subaccount_number}")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(test_account())
