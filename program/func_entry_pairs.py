from constants import ZSCORE_THRESH, USD_PER_TRADE, USD_MIN_COLLATERAL, TRADE_SPECIFIC_PAIRS, SPECIFIC_PAIRS
from func_utils import format_number
from func_cointegration import calculate_zscore
from func_public import get_candles_recent
from func_private import get_open_positions, get_account, place_market_order
import pandas as pd
import json

IGNORE_ASSETS = ["BTC-USD_x", "BTC-USD_y"]

# Define is_market_open function
async def is_market_open(client, market):
    open_positions = await get_open_positions(client)
    return market in open_positions.keys()

# Fetch market data directly
async def fetch_market_data(client, market):
    try:
        response = await client.indexer.markets.get_perpetual_markets()
        return response["markets"].get(market, None)
    except Exception as e:
        print(f"Error fetching market data for {market}: {e}")
        return None

# Function to open positions based on cointegration signals
async def open_positions(client):
    """
    Manage finding triggers for trade entry.
    Store trades for managing later on for the exit function.
    """

    # Load cointegrated pairs
    df = pd.read_csv("cointegrated_pairs.csv")

    bot_agents = []

    # Load existing bot agents from JSON
    try:
        with open("bot_agents.json", "r") as open_positions_file:
            open_positions_dict = json.load(open_positions_file)
            for p in open_positions_dict:
                bot_agents.append(p)
    except FileNotFoundError:
        bot_agents = []

    # Get all available markets from the exchange
    markets_response = await client.indexer.markets.get_perpetual_markets()
    available_markets = markets_response["markets"].keys()

    # Loop through pairs to find opportunities
    for _, row in df.iterrows():
        base_market = row["base_market"]
        quote_market = row["quote_market"]

        # Skip invalid or unavailable markets
        if base_market not in available_markets or quote_market not in available_markets:
            print(f"Skipping invalid or unavailable market pair: {base_market}/{quote_market}")
            continue

        hedge_ratio = row["hedge_ratio"]
        half_life = row["half_life"]

        try:
            series_1 = await get_candles_recent(client, base_market)
            series_2 = await get_candles_recent(client, quote_market)
        except Exception as e:
            print(f"Error fetching prices: {e}")
            continue

        if len(series_1) > 0 and len(series_1) == len(series_2):
            spread = series_1 - (hedge_ratio * series_2)
            z_score = calculate_zscore(spread).values.tolist()[-1]

            if abs(z_score) >= ZSCORE_THRESH:
                base_side = "BUY" if z_score < 0 else "SELL"
                quote_side = "BUY" if z_score > 0 else "SELL"

                base_price = series_1[-1]
                quote_price = series_2[-1]
                base_size = 1 / base_price * USD_PER_TRADE
                quote_size = 1 / quote_price * USD_PER_TRADE

                # Check account balance
                account = await get_account(client)
                free_collateral = float(account["freeCollateral"])
                print(f"Balance: {free_collateral} and minimum at {USD_MIN_COLLATERAL}")

                if free_collateral < USD_MIN_COLLATERAL:
                    print("Insufficient collateral to place the trade.")
                    break

                # Place the base order
                base_order_result = await place_market_order(client, base_market, base_side, base_size, base_price, False)
                if base_order_result["status"] == "failed":
                    print(f"Error placing base order: {base_order_result['error']}")
                    continue
                else:
                    print(f"First order placed successfully for {base_market}: {base_order_result['order_id']}")

                # Place the quote order
                quote_order_result = await place_market_order(client, quote_market, quote_side, quote_size, quote_price, False)
                if quote_order_result["status"] == "failed":
                    print(f"Error placing quote order: {quote_order_result['error']}")
                    continue
                else:
                    print(f"Second order placed successfully for {quote_market}: {quote_order_result['order_id']}")

                # Create Bot Agent
                bot_agent = {
                    "market_1": base_market,
                    "market_2": quote_market,
                    "order_id_m1": base_order_result['order_id'],
                    "order_id_m2": quote_order_result['order_id'],
                    "order_m1_size": base_size,
                    "order_m2_size": quote_size,
                    "order_m1_side": base_side,
                    "order_m2_side": quote_side,
                    "price_m1": base_price,  # Save price for market_1
                    "price_m2": quote_price,  # Save price for market_2
                    "hedge_ratio": hedge_ratio,
                    "z_score": z_score,
                    "half_life": half_life,
                    "pair_status": "LIVE"
                }

                # Append bot agent and save
                bot_agents.append(bot_agent)
                with open("bot_agents.json", "w") as f:
                    json.dump(bot_agents, f)

                print("Trade opened successfully.")
