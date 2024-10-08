from constants import ZSCORE_THRESH, USD_PER_TRADE, USD_MIN_COLLATERAL, TRADE_SPECIFIC_PAIRS, SPECIFIC_PAIRS
from func_utils import format_number
from func_cointegration import calculate_zscore
from func_public import get_candles_recent
from func_private import get_open_positions, get_account, place_market_order
from func_bot_agent import BotAgent
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
        return response["markets"][market]
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

    # Loop through pairs to find opportunities
    for _, row in df.iterrows():
        base_market = row["base_market"]
        quote_market = row["quote_market"]

        # Check if TRADE_SPECIFIC_PAIRS is True and filter out non-specific pairs
        if TRADE_SPECIFIC_PAIRS and (base_market not in SPECIFIC_PAIRS or quote_market not in SPECIFIC_PAIRS):
            continue

        hedge_ratio = row["hedge_ratio"]
        half_life = row["half_life"]

        if base_market in IGNORE_ASSETS or quote_market in IGNORE_ASSETS:
            continue

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
                is_base_open = await is_market_open(client, base_market)
                is_quote_open = await is_market_open(client, quote_market)

                if not is_base_open and not is_quote_open:
                    base_side = "BUY" if z_score < 0 else "SELL"
                    quote_side = "BUY" if z_score > 0 else "SELL"

                    base_price = series_1[-1]
                    quote_price = series_2[-1]
                    accept_base_price = float(base_price) * 1.01 if z_score < 0 else float(base_price) * 0.99
                    accept_quote_price = float(quote_price) * 1.01 if z_score > 0 else float(quote_price) * 0.99

                    failsafe_base_price = float(base_price) * 0.05 if z_score < 0 else float(base_price) * 1.7

                    # Fetch market data for both base and quote markets
                    market_base_data = await fetch_market_data(client, base_market)
                    market_quote_data = await fetch_market_data(client, quote_market)

                    if market_base_data is None or market_quote_data is None:
                        print(f"Error fetching market data for {base_market} or {quote_market}")
                        continue

                    base_tick_size = market_base_data["tickSize"]
                    quote_tick_size = market_quote_data["tickSize"]

                    accept_base_price = format_number(accept_base_price, base_tick_size)
                    accept_quote_price = format_number(accept_quote_price, quote_tick_size)
                    accept_failsafe_base_price = format_number(failsafe_base_price, base_tick_size)

                    base_quantity = 1 / base_price * USD_PER_TRADE
                    quote_quantity = 1 / quote_price * USD_PER_TRADE

                    base_step_size = market_base_data["stepSize"]
                    quote_step_size = market_quote_data["stepSize"]

                    base_size = format_number(base_quantity, base_step_size)
                    quote_size = format_number(quote_quantity, quote_step_size)

                    account = await get_account(client)
                    free_collateral = float(account["freeCollateral"])

                    if free_collateral < USD_MIN_COLLATERAL:
                        print("Insufficient collateral to place the trade.")
                        break

                    # Place the base order
                    base_order_result = await place_market_order(client, base_market, base_side, base_size, accept_base_price, False)
                    if base_order_result["status"] == "failed":
                        print(f"Error placing base order: {base_order_result['error']}")
                        continue
                    else:
                        print(f"First order placed successfully for {base_market}: {base_order_result['order_id']}")

                    # Place the quote order
                    quote_order_result = await place_market_order(client, quote_market, quote_side, quote_size, accept_quote_price, False)
         
