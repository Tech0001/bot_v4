# Imports
import random
import time
import json
import pandas as pd
import asyncio
from dydx_v4_client.node.market import Market
from dydx_v4_client.indexer.rest.constants import OrderType
from dydx_v4_client.indexer.rest.indexer_client import IndexerClient
from func_utils import format_number
from func_cointegration import calculate_zscore
from func_private import get_open_positions
from func_bot_agent import BotAgent

# Constants (update these as needed for your setup)
IGNORE_ASSETS = [""]  # Add assets to ignore if necessary
ZSCORE_THRESH = 2  # Example threshold for Z-Score entry
USD_PER_TRADE = 100  # Adjust per your trading size
USD_MIN_COLLATERAL = 50  # Minimum collateral required for a trade

# Initialize IndexerClient for fetching market data and positions
indexer_client = IndexerClient(
    node_url="https://testnet.dydx.exchange",  # Ensure correct node URL
    network_id="testnet"  # Example for testnet
)

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

# Fetch recent candles for a market
async def get_candles_recent(client, market):
    try:
        response = await client.get_candles(
            market=market,
            resolution="1HOUR"  # Use a stable resolution such as 1HOUR
        )
        candles = response.get("candles", [])
        if candles:
            return [float(candle["close"]) for candle in candles]  # Return closing prices as float
        else:
            print(f"No candles found for {market}")
            return None
    except Exception as e:
        print(f"Error fetching candles for {market}: {e}")
        return None

# Open positions function - manage finding triggers for trade entry
async def open_positions(client):
    """
    Manage finding triggers for trade entry
    Store trades for managing later on in the exit function
    """

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
        if series_1 and series_2 and len(series_1) > 0 and len(series_1) == len(series_2):
            try:
                # Ensure values in series_1 and series_2 are floats before calculating spread
                spread = [float(s1) - (hedge_ratio * float(s2)) for s1, s2 in zip(series_1, series_2)]  # Calculate spread
                z_score = calculate_zscore(spread).values.tolist()[-1]  # Ensure z_score is calculated correctly
            except TypeError as te:
                print(f"Error calculating spread or z-score: {te}")
                continue

            # Check if the trade trigger meets the z-score threshold
            if abs(z_score) >= ZSCORE_THRESH:

                # Ensure that positions are not already open for the pair
                is_base_open = await is_open_positions(indexer_client, base_market)
                is_quote_open = await is_open_positions(indexer_client, quote_market)

                if not is_base_open and not is_quote_open:

                    # Determine trade sides
                    base_side = "BUY" if z_score < 0 else "SELL"
                    quote_side = "BUY" if z_score > 0 else "SELL"

                    # Fetch market data directly for size and price calculations
                    try:
                        base_market_data = await client.get_market(market=base_market)
                        quote_market_data = await client.get_market(market=quote_market)
                    except Exception as e:
                        print(f"Error fetching market data for {base_market} or {quote_market}: {e}")
                        continue

                    # Calculate acceptable price and size for each market
                    base_price = series_1[-1]
                    quote_price = series_2[-1]
                    accept_base_price = format_number(float(base_price) * (1.01 if z_score < 0 else 0.99), base_market_data["tickSize"])
                    accept_quote_price = format_number(float(quote_price) * (1.01 if z_score > 0 else 0.99), quote_market_data["tickSize"])
                    base_quantity = 1 / base_price * USD_PER_TRADE
                    quote_quantity = 1 / quote_price * USD_PER_TRADE
                    base_size = format_number(base_quantity, base_market_data["stepSize"])
                    quote_size = format_number(quote_quantity, quote_market_data["stepSize"])

                    # Ensure minimum order size
                    base_min_order_size = 1 / float(base_market_data["oraclePrice"])
                    quote_min_order_size = 1 / float(quote_market_data["oraclePrice"])

                    if float(base_quantity) > base_min_order_size and float(quote_quantity) > quote_min_order_size:

                        # Create BotAgent and open trades
                        bot_agent = BotAgent(
                            client,
                            market_1=base_market,
                            market_2=quote_market,
                            base_side=base_side,
                            base_size=base_size,
                            base_price=accept_base_price,
                            quote_side=quote_side,
                            quote_size=quote_size,
                            quote_price=accept_quote_price,
                            z_score=z_score,
                            half_life=half_life,
                            hedge_ratio=hedge_ratio
                        )

                        # Attempt to open trades
                        bot_open_dict = await bot_agent.open_trades()

                        # Check for 'createdAtHeight' in the response
                        if "createdAtHeight" in bot_open_dict:
                            created_at_height = bot_open_dict["createdAtHeight"]
                            print(f"Order created at height: {created_at_height}")
                        else:
                            print("Notice: 'createdAtHeight' not found in the order response. Proceeding without it.")
                            if "id" in bot_open_dict:
                                print(f"Order ID: {bot_open_dict['id']}")
                            if "status" in bot_open_dict:
                                print(f"Order Status: {bot_open_dict['status']}")

                        # Confirm the trade is live
                        if bot_open_dict.get("pair_status") == "LIVE":
                            bot_agents.append(bot_open_dict)

                            # Save the trade to JSON file
                            with open("bot_agents.json", "w") as f:
                                json.dump(bot_agents, f)

                            print(f"Trade status: Live for {base_market} - {quote_market}")

    # Save agents to the file
    print("Success: All open trades checked")
