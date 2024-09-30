# Import necessary functions and constants
import numpy as np
import pandas as pd
import json
from func_private import get_open_positions, get_account
from func_public import get_candles_recent, get_markets
from func_cointegration import calculate_zscore
from constants import ZSCORE_THRESH, USD_PER_TRADE, USD_MIN_COLLATERAL
from func_utils import format_number

# Define some IGNORE_ASSETS (example)
IGNORE_ASSETS = ["BTC-USD_x", "BTC-USD_y"]

# Function to manage finding trading opportunities and opening positions
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
    
    print("Iterating over cointegrated pairs...")
    
    for index, row in df.iterrows():
        base_market = row["base_market"]
        quote_market = row["quote_market"]
        hedge_ratio = row["hedge_ratio"]

        # Check if the market pair is to be ignored
        if base_market in IGNORE_ASSETS or quote_market in IGNORE_ASSETS:
            continue

        try:
            series_1 = await get_candles_recent(client, base_market)
            series_2 = await get_candles_recent(client, quote_market)
        except:
            continue

        if len(series_1) > 0 and len(series_1) == len(series_2):
            spread = np.array(series_1) - hedge_ratio * np.array(series_2)
            z_score = calculate_zscore(spread).values.tolist()[-1]

            if abs(z_score) >= ZSCORE_THRESH:
                is_base_open = await get_open_positions(client)
                is_quote_open = await get_open_positions(client)

                if not is_base_open and not is_quote_open:
                    base_side = "BUY" if z_score < 0 else "SELL"
                    quote_side = "BUY" if z_score > 0 else "SELL"

                    base_price = float(series_1[-1])
                    quote_price = float(series_2[-1])
                    base_size = format_number(1 / base_price * USD_PER_TRADE, markets["markets"][base_market]["stepSize"])
                    quote_size = format_number(1 / quote_price * USD_PER_TRADE, markets["markets"][quote_market]["stepSize"])

                    # Ensure size is valid
                    if float(base_size) > 1 / float(markets["markets"][base_market]["oraclePrice"]) and float(quote_size) > 1 / float(markets["markets"][quote_market]["oraclePrice"]):
                        print(f"Placing trades for {base_market} and {quote_market}")
                        # Call the trading functions here...
                        bot_agents.append({
                            "base_market": base_market,
                            "quote_market": quote_market,
                            "base_side": base_side,
                            "quote_side": quote_side
                        })

    # Save bot agents to file
    with open("bot_agents.json", "w") as f:
        json.dump(bot_agents, f)
    print("Completed trade opportunities search.")
