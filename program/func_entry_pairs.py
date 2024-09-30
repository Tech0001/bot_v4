from constants import ZSCORE_THRESH, USD_PER_TRADE, USD_MIN_COLLATERAL
from func_utils import format_number
from func_cointegration import calculate_zscore
from func_public import get_candles_recent, get_markets
from func_private import is_open_positions, get_account
from func_bot_agent import BotAgent
import pandas as pd
import json

from pprint import pprint

IGNORE_ASSETS = ["BTC-USD_x", "BTC-USD_y"]  # Ignore these assets which are not trading on testnet

# Open positions
async def open_positions(client):
    """
    Manage finding triggers for trade entry
    Store trades for managing later on in the exit function
    """

    # Load cointegrated pairs
    df = pd.read_csv("cointegrated_pairs.csv")

    # Get markets for reference (min order size, tick size, etc.)
    markets = await get_markets(client)

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
        hedge_ratio = row["hedge_ratio"]
        half_life = row["half_life"]

        # Skip ignored assets
        if base_market in IGNORE_ASSETS or quote_market in IGNORE_ASSETS:
            continue

        # Get recent prices
        try:
            series_1 = await get_candles_recent(client, base_market)
            series_2 = await get_candles_recent(client, quote_market)
        except Exception as e:
            print(f"Error fetching data for {base_market} or {quote_market}: {e}")
            continue

        # Ensure data length is the same and calculate z-score
        if len(series_1) > 0 and len(series_1) == len(series_2):
            spread = series_1 - (hedge_ratio * series_2)
            z_score = calculate_zscore(spread).values.tolist()[-1]

            # Check if the trade trigger meets the z-score threshold
            if abs(z_score) >= ZSCORE_THRESH:

                # Ensure that positions are not already open for the pair
                is_base_open = await is_open_positions(client, base_market)
                is_quote_open = await is_open_positions(client, quote_market)

                if not is_base_open and not is_quote_open:

                    # Determine trade sides
                    base_side = "BUY" if z_score < 0 else "SELL"
                    quote_side = "BUY" if z_score > 0 else "SELL"

                    # Calculate acceptable price and size for each market
                    base_price = series_1[-1]
                    quote_price = series_2[-1]
                    accept_base_price = format_number(float(base_price) * (1.01 if z_score < 0 else 0.99), markets["markets"][base_market]["tickSize"])
                    accept_quote_price = format_number(float(quote_price) * (1.01 if z_score > 0 else 0.99), markets["markets"][quote_market]["tickSize"])
                    base_quantity = 1 / base_price * USD_PER_TRADE
                    quote_quantity = 1 / quote_price * USD_PER_TRADE
                    base_size = format_number(base_quantity, markets["markets"][base_market]["stepSize"])
                    quote_size = format_number(quote_quantity, markets["markets"][quote_market]["stepSize"])

                    # Ensure minimum order size
                    base_min_order_size = 1 / float(markets["markets"][base_market]["oraclePrice"])
                    quote_min_order_size = 1 / float(markets["markets"][quote_market]["oraclePrice"])

                    if float(base_quantity) > base_min_order_size and float(quote_quantity) > quote_min_order_size:

                        # Check account balance
                        account = await get_account(client)
                        free_collateral = float(account["freeCollateral"])
                        print(f"Balance: {free_collateral}, Minimum Required: {USD_MIN_COLLATERAL}")

                        # Guard: Ensure sufficient collateral
                        if free_collateral < USD_MIN_COLLATERAL:
                            print("Insufficient collateral. Skipping trade.")
                            continue

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
                            accept_failsafe_base_price=format_number(float(base_price) * (0.05 if z_score < 0 else 1.7), markets["markets"][base_market]["tickSize"]),
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
                            print("Error: 'createdAtHeight' not found in the order response")

                        # Handle failure in opening trades
                        if bot_open_dict == "failed":
                            continue

                        # Confirm the trade is live
                        if bot_open_dict["pair_status"] == "LIVE":
                            bot_agents.append(bot_open_dict)

                            # Save the trade to JSON file
                            with open("bot_agents.json", "w") as f:
                                json.dump(bot_agents, f)

                            print(f"Trade status: Live for {base_market} - {quote_market}")

    # Save agents to the file
    print("Success: All open trades checked")
