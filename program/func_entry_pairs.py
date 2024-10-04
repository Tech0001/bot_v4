from constants import ZSCORE_THRESH, USD_PER_TRADE, USD_MIN_COLLATERAL
from func_utils import format_number
from func_cointegration import calculate_zscore
from func_public import get_candles_recent, get_markets
from func_private import is_open_positions, get_account
from func_bot_agent import BotAgent
import pandas as pd
import json
import time
import asyncio

IGNORE_ASSETS = ["BTC-USD_x", "BTC-USD_y"]  # Ignore these assets which are not trading on testnet

# Open positions
async def open_positions(client):
    """
    Manage finding triggers for trade entry.
    Store trades for managing later on for the exit function.
    """

    # Load cointegrated pairs
    df = pd.read_csv("cointegrated_pairs.csv")

    # Get markets for reference (min order size, tick size, etc.)
    markets = await get_markets(client)

    # Initialize container for BotAgent results
    bot_agents = []

    # Opening JSON file
    try:
        with open("bot_agents.json", "r") as open_positions_file:
            open_positions_dict = json.load(open_positions_file)
            for p in open_positions_dict:
                bot_agents.append(p)
    except FileNotFoundError:
        bot_agents = []
    except Exception:
        bot_agents = []

    # Find ZScore triggers
    for index, row in df.iterrows():

        # Extract variables
        base_market = row["base_market"]
        quote_market = row["quote_market"]
        hedge_ratio = row["hedge_ratio"]
        half_life = row["half_life"]

        # Continue if ignore asset
        if base_market in IGNORE_ASSETS or quote_market in IGNORE_ASSETS:
            continue

        # Get prices with a maximum candle length of 400 hours
        try:
            series_1 = await get_candles_recent(client, base_market, 400)
            series_2 = await get_candles_recent(client, quote_market, 400)
        except Exception:
            continue

        # Get ZScore
        if len(series_1) > 0 and len(series_1) == len(series_2):
            spread = series_1 - (hedge_ratio * series_2)
            z_score = calculate_zscore(spread).values.tolist()[-1]

            # Log whether the ZScore exceeds the threshold
            print(f"ZScore for {base_market}/{quote_market}: {z_score}")
            if abs(z_score) >= ZSCORE_THRESH:
                print(f"ZScore of {z_score} exceeds threshold of {ZSCORE_THRESH}. Considering trade.")

                # Ensure like-for-like not already open (diversify trading)
                is_base_open = await is_open_positions(client, base_market)
                is_quote_open = await is_open_positions(client, quote_market)

                # If no open positions, proceed to trade
                if not is_base_open and not is_quote_open:
                    print(f"No open positions for {base_market}/{quote_market}. Placing trade.")

                    # Determine side
                    base_side = "BUY" if z_score < 0 else "SELL"
                    quote_side = "BUY" if z_score > 0 else "SELL"

                    # Get acceptable price in string format with correct number of decimals
                    base_price = series_1[-1]
                    quote_price = series_2[-1]
                    accept_base_price = float(base_price) * 1.01 if z_score < 0 else float(base_price) * 0.99
                    accept_quote_price = float(quote_price) * 1.01 if z_score > 0 else float(quote_price) * 0.99
                    failsafe_base_price = float(base_price) * 0.05 if z_score < 0 else float(base_price) * 1.7
                    base_tick_size = markets["markets"][base_market]["tickSize"]
                    quote_tick_size = markets["markets"][quote_market]["tickSize"]

                    # Format prices
                    accept_base_price = format_number(accept_base_price, base_tick_size)
                    accept_quote_price = format_number(accept_quote_price, quote_tick_size)
                    accept_failsafe_base_price = format_number(failsafe_base_price, base_tick_size)

                    # Get size
                    base_quantity = 1 / base_price * USD_PER_TRADE
                    quote_quantity = 1 / quote_price * USD_PER_TRADE
                    base_step_size = markets["markets"][base_market]["stepSize"]
                    quote_step_size = markets["markets"][quote_market]["stepSize"]

                    # Format sizes
                    base_size = format_number(base_quantity, base_step_size)
                    quote_size = format_number(quote_quantity, quote_step_size)

                    # Ensure size (minimum order size greater than $1 according to V4 documentation)
                    base_min_order_size = 1 / float(markets["markets"][base_market]["oraclePrice"])
                    quote_min_order_size = 1 / float(markets["markets"][quote_market]["oraclePrice"])

                    # Combine checks
                    check_base = float(base_quantity) > base_min_order_size
                    check_quote = float(quote_quantity) > quote_min_order_size

                    # If checks pass, place trades
                    if check_base and check_quote:
                        print(f"Order size checks passed for {base_market}/{quote_market}.")

                        # Check account balance
                        account = await get_account(client)
                        free_collateral = float(account["freeCollateral"])
                        print(f"Balance: {free_collateral} and minimum at {USD_MIN_COLLATERAL}")

                        # Guard: Ensure collateral
                        if free_collateral < USD_MIN_COLLATERAL:
                            print("Insufficient collateral. Skipping trade.")
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
                            accept_failsafe_base_price=accept_failsafe_base_price,
                            z_score=z_score,
                            half_life=half_life,
                            hedge_ratio=hedge_ratio
                        )

                        # Open Trades
                        bot_open_dict = await bot_agent.open_trades()

                        # Guard: Handle failure
                        if bot_open_dict == "failed":
                            print("Failed to open trades.")
                            continue

                        # Handle success in opening trades
                        if bot_open_dict["pair_status"] == "LIVE":
                            print("Trade status: Live")

                            # Append to list of bot agents
                            bot_agents.append(bot_open_dict)
                            del(bot_open_dict)

                            # Save trade
                            with open("bot_agents.json", "w") as f:
                                json.dump(bot_agents, f)

    # Add sleep delay to reduce looping
    await asyncio.sleep(1)

    # Save agents
    # if len(bot_agents) > 0:
    #   with open("bot_agents.json", "w") as f:
    #     json.dump(bot_agents, f)
