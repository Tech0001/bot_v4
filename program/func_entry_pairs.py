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

# Fetch market data once at the start of the process
async def get_markets(client):
    try:
        response = await client.indexer.markets.get_perpetual_markets()
        if "markets" in response:
            return response
        else:
            raise ValueError("Markets data not available.")
    except Exception as e:
        print(f"Error fetching markets data: {e}")
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

    # Fetch markets data at the start
    markets = await get_markets(client)
    if markets is None:
        print("Error: Could not retrieve markets data.")
        return

    if "markets" not in markets:
        print("Error: Markets data not available.")
        return

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
            print(f"Error fetching prices for {base_market} or {quote_market}: {e}")
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

                    # Fetch tick size and step size from pre-fetched markets data
                    try:
                        base_tick_size = markets["markets"][base_market]["tickSize"]
                        quote_tick_size = markets["markets"][quote_market]["tickSize"]

                        base_step_size = markets["markets"][base_market]["stepSize"]
                        quote_step_size = markets["markets"][quote_market]["stepSize"]

                        base_min_order_size = 1 / float(markets["markets"][base_market]["oraclePrice"])
                        quote_min_order_size = 1 / float(markets["markets"][quote_market]["oraclePrice"])
                    except KeyError:
                        print(f"Error: Market data not found for {base_market} or {quote_market}")
                        continue

                    # Format prices
                    accept_base_price = format_number(accept_base_price, base_tick_size)
                    accept_quote_price = format_number(accept_quote_price, quote_tick_size)
                    accept_failsafe_base_price = format_number(failsafe_base_price, base_tick_size)

                    # Get size
                    base_quantity = 1 / base_price * USD_PER_TRADE
                    quote_quantity = 1 / quote_price * USD_PER_TRADE

                    # Format sizes
                    base_size = format_number(base_quantity, base_step_size)
                    quote_size = format_number(quote_quantity, quote_step_size)

                    # Ensure order sizes are greater than the minimum allowed size
                    if float(base_quantity) < base_min_order_size or float(quote_quantity) < quote_min_order_size:
                        print(f"Trade size too small for {base_market} or {quote_market}")
                        continue

                    # Check account balance
                    account = await get_account(client)
                    free_collateral = float(account["freeCollateral"])

                    if free_collateral < USD_MIN_COLLATERAL:
                        print(f"Insufficient collateral to place the trade for {base_market} and {quote_market}.")
                        continue

                    # Place the base order
                    base_order_result = await place_market_order(client, base_market, base_side, base_size, accept_base_price, False)
                    if base_order_result["status"] == "failed":
                        print(f"Error placing base order for {base_market}: {base_order_result['error']}")
                        continue
                    else:
                        print(f"First order placed successfully for {base_market}: {base_order_result['order_id']}")

                    # Place the quote order
                    quote_order_result = await place_market_order(client, quote_market, quote_side, quote_size, accept_quote_price, False)
                    if quote_order_result["status"] == "failed":
                        print(f"Error placing quote order for {quote_market}: {quote_order_result['error']}")
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
                        print(f"Trade opened successfully for {base_market} and {quote_market}.")
