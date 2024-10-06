from constants import ZSCORE_THRESH, USD_PER_TRADE, USD_MIN_COLLATERAL
from func_utils import format_number
from func_cointegration import calculate_zscore
from func_public import get_candles_recent
from func_private import get_open_positions, get_account, place_market_order
from func_bot_agent import BotAgent
import pandas as pd
import json

IGNORE_ASSETS = ["BTC-USD_x", "BTC-USD_y"]

# Helper function to check if a market has an open position
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
    for index, row in df.iterrows():
        base_market = row["base_market"]
        quote_market = row["quote_market"]
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

            # Initialize base_side and quote_side safely
            base_side, quote_side = None, None

            if abs(z_score) >= ZSCORE_THRESH:
                is_base_open = await is_market_open(client, base_market)
                is_quote_open = await is_market_open(client, quote_market)

                # Fetch account details
                account = await get_account(client)

                # Log the complete asset positions
                print(f"Full account data for assets: {account['assetPositions']}")

                # Fetch holdings for the base and quote markets
                asset_positions = account['assetPositions']

                # Standardize asset symbols for comparison
                base_symbol = base_market.replace("-USD", "").upper()
                quote_symbol = quote_market.replace("-USD", "").upper()

                # Attempt to find the symbol in multiple ways to avoid mismatches
                base_holding = float(asset_positions.get(base_symbol, {'size': '0'})['size'])
                quote_holding = float(asset_positions.get(quote_symbol, {'size': '0'})['size'])

                print(f"Checking holdings for {base_market} ({base_symbol}): {base_holding} and {quote_market} ({quote_symbol}): {quote_holding}")

                # Set base_side and quote_side early
                base_side = "BUY" if z_score < 0 else "SELL"
                quote_side = "BUY" if z_score > 0 else "SELL"

                # Check if you have enough base and quote holdings before placing a sell order
                if base_side == "SELL" and base_holding == 0:
                    print(f"Skipping {base_market} sell order: No holdings found.")
                    continue

                if quote_side == "SELL" and quote_holding == 0:
                    print(f"Skipping {quote_market} sell order: No holdings found.")
                    continue

                if not is_base_open and not is_quote_open:
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
                    if quote_order_result["status"] == "failed":
                        print(f"Error placing quote order: {quote_order_result['error']}")
                        continue
                    else:
                        print(f"Second order placed successfully for {quote_market}: {quote_order_result['order_id']}")

                    # Create Bot Agent with accept_failsafe_base_price
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
                        accept_failsafe_base_price=accept_failsafe_base_price,
                        z_score=z_score,
                        half_life=half_life,
                        hedge_ratio=hedge_ratio
                    )

                    bot_open_dict = await bot_agent.open_trades()

                    if bot_open_dict == "failed":
                        continue

                    if bot_open_dict["pair_status"] == "LIVE":
                        bot_agents.append(bot_open_dict)
                        with open("bot_agents.json", "w") as f:
                            json.dump(bot_agents, f)
                        print("Trade opened successfully.")
