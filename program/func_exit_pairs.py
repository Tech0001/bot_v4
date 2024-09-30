from constants import CLOSE_AT_ZSCORE_CROSS, DYDX_ADDRESS, MAX_CLIENT_ID
from func_utils import format_number
from func_cointegration import calculate_zscore
from func_public import get_candles_recent, get_markets
from func_private import place_market_order, get_open_positions, get_order
from dydx_v4_client import Order, OrderFlags
from dydx_v4_client.indexer.rest.constants import OrderType
import random
import time
import json

# Manage trade exits
async def manage_trade_exits(client):
    """
    Manage exiting open positions
    Based upon criteria set in constants
    """

    # Initialize saving output
    save_output = []

    # Open JSON file for current open positions
    try:
        with open("bot_agents.json") as open_positions_file:
            open_positions_dict = json.load(open_positions_file)
    except FileNotFoundError:
        return "complete"

    # Guard: Exit if no open positions in file
    if len(open_positions_dict) < 1:
        return "complete"

    # Get all open positions per trading platform
    exchange_pos = await get_open_positions(client)

    # Create live position tickers list
    markets_live = list(exchange_pos.keys())

    # Protect API rate limits
    time.sleep(0.5)

    # Iterate through all saved positions
    for position in open_positions_dict:

        # Initialize is_close trigger
        is_close = False

        # Extract position matching information from file - market 1
        position_market_m1 = position["market_1"]
        position_size_m1 = position["order_m1_size"]
        position_side_m1 = position["order_m1_side"]

        # Extract position matching information from file - market 2
        position_market_m2 = position["market_2"]
        position_size_m2 = position["order_m2_size"]
        position_side_m2 = position["order_m2_side"]

        # Protect API
        time.sleep(0.5)

        # Get order info for market 1
        order_m1 = await get_order(client, position.get("order_id_m1"))
        if not order_m1 or "ticker" not in order_m1:
            print(f"Error: Invalid order_id or missing details for {position_market_m1}. Skipping this position.")
            continue

        order_market_m1 = order_m1.get("ticker", None)
        order_size_m1 = order_m1.get("size", None)
        order_side_m1 = order_m1.get("side", None)

        # Get order info for market 2
        order_m2 = await get_order(client, position.get("order_id_m2"))
        if not order_m2 or "ticker" not in order_m2:
            print(f"Error: Invalid order_id or missing details for {position_market_m2}. Skipping this position.")
            continue

        order_market_m2 = order_m2.get("ticker", None)
        order_size_m2 = order_m2.get("size", None)
        order_side_m2 = order_m2.get("side", None)

        ## Ensure sizes match what was sent to the exchange
        position_size_m1 = order_size_m1
        position_size_m2 = order_size_m2

        # Perform matching checks
        check_m1 = (position_market_m1 == order_market_m1 and position_size_m1 == order_size_m1 and position_side_m1 == order_side_m1)
        check_m2 = (position_market_m2 == order_market_m2 and position_size_m2 == order_size_m2 and position_side_m2 == order_side_m2)
        check_live = position_market_m1 in markets_live and position_market_m2 in markets_live

        # Log mismatches but continue running the bot
        if not (check_m1 and check_m2 and check_live):
            print(f"Warning: Mismatch detected for {position_market_m1} and {position_market_m2}.")
            print(f"Details: Position size or side may not match exactly.")
            continue  # Skip mismatched positions but do not stop the bot

        # Get prices and check exit logic
        series_1 = await get_candles_recent(client, position_market_m1)
        series_2 = await get_candles_recent(client, position_market_m2)

        # Get markets for reference of tick size
        markets = await get_markets(client)

        # Protect API rate limits
        time.sleep(0.2)

        # Trigger close based on Z-Score
        if CLOSE_AT_ZSCORE_CROSS:
            hedge_ratio = position["hedge_ratio"]
            z_score_traded = position["z_score"]
            if len(series_1) > 0 and len(series_1) == len(series_2):
                spread = series_1 - (hedge_ratio * series_2)
                z_score_current = calculate_zscore(spread).values.tolist()[-1]

            # Determine trigger for Z-Score cross
            z_score_level_check = abs(z_score_current) >= abs(z_score_traded)
            z_score_cross_check = (z_score_current < 0 and z_score_traded > 0) or (z_score_current > 0 and z_score_traded < 0)

            if z_score_level_check and z_score_cross_check:
                is_close = True

        # Add any other custom exit logic here if needed

        # Close positions if triggered
        if is_close:
            side_m1 = "SELL" if position_side_m1 == "BUY" else "BUY"
            side_m2 = "SELL" if position_side_m2 == "BUY" else "BUY"

            price_m1 = float(series_1[-1])
            price_m2 = float(series_2[-1])
            accept_price_m1 = format_number(price_m1 * 1.05 if side_m1 == "BUY" else price_m1 * 0.95, markets["markets"][position_market_m1]["tickSize"])
            accept_price_m2 = format_number(price_m2 * 1.05 if side_m2 == "BUY" else price_m2 * 0.95, markets["markets"][position_market_m2]["tickSize"])

            try:
                print(f"Closing position for {position_market_m1}")
                close_order_m1, _ = await place_market_order(client, position_market_m1, side_m1, position_size_m1, accept_price_m1, True)
                if not close_order_m1:
                    print(f"Failed to place order to close position for {position_market_m1}")
                    continue

                print(f"Closing position for {position_market_m2}")
                close_order_m2, _ = await place_market_order(client, position_market_m2, side_m2, position_size_m2, accept_price_m2, True)
                if not close_order_m2:
                    print(f"Failed to place order to close position for {position_market_m2}")
                    continue

            except Exception as e:
                print(f"Error while trying to close positions for {position_market_m1} and {position_market_m2}: {e}")
                save_output.append(position)

        else:
            save_output.append(position)

    # Save remaining items
    with open("bot_agents.json", "w") as f:
        json.dump(save_output, f)

    return "complete"
