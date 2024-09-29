# Import necessary functions and constants
from func_private import get_open_positions, get_account
from func_public import get_candles_recent, get_markets
from func_cointegration import calculate_zscore
from constants import ZSCORE_THRESH, USD_PER_TRADE, USD_MIN_COLLATERAL  # Fixed import
from func_utils import format_number
from func_bot_agent import BotAgent  # Fixed import
import pandas as pd
import json

# Define some IGNORE_ASSETS (example)
IGNORE_ASSETS = ["BTC-USD_x", "BTC-USD_y"]

# Open positions
async def open_positions(client):
    """
    Function to manage finding trading opportunities and opening positions
    """
    df = pd.read_csv("cointegrated_pairs.csv")
    markets = await get_markets(client)
    bot_agents = []

    # Load existing agents if they exist
    try:
        with open("bot_agents.json", "r") as f:
            bot_agents = json.load(f)
    except FileNotFoundError:
        bot_agents = []

    for index, row in df.iterrows():
        base_market = row["base_market"]
        quote_market = row["quote_market"]
        hedge_ratio = row["hedge_ratio"]

        if base_market in IGNORE_ASSETS or quote_market in IGNORE_ASSETS:
            continue

        try:
            series_1 = await get_candles_recent(client, base_market)
            series_2 = await get_candles_recent(client, quote_market)
        except Exception as e:
            print(f"Error fetching candles: {e}")
            continue

        if len(series_1) > 0 and len(series_1) == len(series_2):
            spread = series_1 - (hedge_ratio * series_2)
            z_score = calculate_zscore(spread).values.tolist()[-1]

            if abs(z_score) >= ZSCORE_THRESH:
                is_base_open = await get_open_positions(client)
                is_quote_open = await get_open_positions(client)

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

                    check_base = float(base_quantity) > 1 / float(markets["markets"][base_market]["oraclePrice"])
                    check_quote = float(quote_quantity) > 1 / float(markets["markets"][quote_market]["oraclePrice"])

                    if check_base and check_quote:
                        account = await get_account(client)
                        free_collateral = float(account["freeCollateral"])

                        if free_collateral < USD_MIN_COLLATERAL:
                            print("Insufficient collateral.")
                            continue

                        # Initialize the BotAgent
                        bot_agent = BotAgent(
                            client=client,
                            market_1=base_market,
                            market_2=quote_market,
                            base_side=base_side,
                            base_size=base_size,
                            base_price=accept_base_price,
                            quote_side=quote_side,
                            quote_size=quote_size,
                            quote_price=accept_quote_price,
                            accept_failsafe_base_price=accept_base_price * 0.9,
                            z_score=z_score,
                            half_life=row["half_life"],
                            hedge_ratio=hedge_ratio
                        )

                        bot_open_dict = await bot_agent.open_trades()

                        if bot_open_dict["pair_status"] == "LIVE":
                            bot_agents.append(bot_open_dict)

    # Save the active bot agents
    with open("bot_agents.json", "w") as f:
        json.dump(bot_agents, f)

    print("Open positions function completed.")
