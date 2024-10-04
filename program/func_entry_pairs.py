from constants import ZSCORE_THRESH, USD_PER_TRADE, USD_MIN_COLLATERAL
from func_utils import format_number
from func_cointegration import calculate_zscore
from func_public import get_candles_recent, get_markets
from func_private import is_open_positions, get_account
from func_bot_agent import BotAgent
import pandas as pd
import json

IGNORE_ASSETS = ["BTC-USD_x", "BTC-USD_y"]

# Function to open positions based on cointegration signals
async def open_positions(client):
    """
    Manage finding triggers for trade entry.
    Store trades for managing later on for the exit function.
    """

    # Load cointegrated pairs
    df = pd.read_csv("cointegrated_pairs.csv")

    # Get markets from referencing min order size, tick size, etc.
    markets = await get_markets(client)

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

            if abs(z_score) >= ZSCORE_THRESH:
                is_base_open = await is_open_positions(client, base_market)
                is_quote_open = await is_open_positions(client, quote_market)

                if not is_base_open and not is_quote_open:
                    base_side = "BUY" if z_score < 0 else "SELL"
                    quote_side = "BUY" if z_score > 0 else "SELL"

                    base_price = series_1[-1]
                    quote_price = series_2[-1]
                    accept_base_price = float(base_price) * 1.01 if z_score < 0 else float(base_price) * 0.99
                    accept_quote_price = float(quote_price) * 1.01 if z_score > 0 else float(quote_price) * 0.99

                    base_tick_size = markets["markets"][base_market]["tickSize"]
                    quote_tick_size = markets["markets"][quote_market]["tickSize"]

                    accept_base_price = format_number(accept_base_price, base_tick_size)
                    accept_quote_price = format_number(accept_quote_price, quote_tick_size)

                    base_quantity = 1 / base_price * USD_PER_TRADE
                    quote_quantity = 1 / quote_price * USD_PER_TRADE

                    base_step_size = markets["markets"][base_market]["stepSize"]
                    quote_step_size = markets["markets"][quote_market]["stepSize"]

                    base_size = format_number(base_quantity, base_step_size)
                    quote_size = format_number(quote_quantity, quote_step_size)

                    account = await get_account(client)
                    free_collateral = float(account["freeCollateral"])

                    if free_collateral < USD_MIN_COLLATERAL:
                        print("Insufficient collateral to place the trade.")
                        break

                    # Create Bot Agent
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

                    bot_open_dict = await bot_agent.open_trades()

                    if bot_open_dict == "failed":
                        continue

                    if bot_open_dict["pair_status"] == "LIVE":
                        bot_agents.append(bot_open_dict)
                        with open("bot_agents.json", "w") as f:
                            json.dump(bot_agents, f)
                        print("Trade opened successfully.")
