# Import necessary functions and constants
import numpy as np
import pandas as pd
import json
from func_private import get_open_positions, get_account
from func_public import get_candles_recent, get_markets
from func_cointegration import calculate_zscore
from constants import ZSCORE_THRESH, USD_PER_TRADE, USD_MIN_COLLATERAL
from func_utils import format_number
import pprint



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
    
    print("Starting to iterate over cointegrated pairs...")
    
    for index, row in df.iterrows():
        base_market = row["base_market"]
        quote_market = row["quote_market"]
        hedge_ratio = row["hedge_ratio"]
        pprint(f"Processing pair: {base_market} - {quote_market} with hedge ratio: {hedge_ratio}")

        # Check if the market pair is to be ignored
        if base_market in IGNORE_ASSETS or quote_market in IGNORE_ASSETS:
            print(f"Ignoring pair: {base_market} - {quote_market}")
            continue

        try:
            series_1 = await get_candles_recent(client, base_market)
            series_2 = await get_candles_recent(client, quote_market)
        except Exception as e:
            print(f"Error fetching candles for {base_market} or {quote_market}: {e}")
            continue

        print
