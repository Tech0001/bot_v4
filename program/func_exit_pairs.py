from constants import CLOSE_AT_ZSCORE_CROSS
from func_utils import format_number
from func_cointegration import calculate_zscore
from func_private import place_market_order, get_open_positions, get_order
from func_public import get_candles_recent, get_markets
import json
import time

# Manage trade exits
async def manage_trade_exits(client):
    """
    Manage exiting open positions based upon criteria set in constants.
    """

    # Initialize saving output
    save_output = []

    # Open JSON file containing open positions
    try:
        with open("bot_agents.json", "r") as open_positions_file:
            open_positions_dict = json.load(open_positions_file)
    except FileNotFoundError:
        return "complete"

    # Guard: Exit if no open positions in file
    if len(open_positions_dict) < 1:
        return "complete"

    # Get all open positions from the trading platform
    exchange_pos = await get_open_positions(client)

    # Create live position tickers list
    markets_live = list(exchange_pos.keys())

    # Protect API rate limit
    time.sleep(0.5)

    # Fetch market data once at the beginning
    markets = await get_markets(client)
    if markets is None or "markets" not in markets:
        print("Error: Markets data not available.")
        return "error"

    # Check all saved positions match order record and apply exit logic
    for position in open_positions_dict:
        # Initialize is_close trigger
        is_close = False

        # Extract position information from file for market 1
        position_market_m1 = position["market_1"]
        position_size_m1 = position["order_m1_size"]
        position_side_m1 = position["order_m1_side"]

        # Extract position information from file for market 2
        position_market_m2 = position["market_2"]
        position_size_m2 = position["order_m2_size"]
        position_side_m2 = position["order_m2_side"]

        # Get order info for market 1
        order_m1 = await get_order(client, position["order_id_m1"])
        if order_m1 is None:
            print(f"Error: Order info for {position_market_m1} not found.")
            continue
        
        order_market_m1 = order_m1["ticker"]
        order_size_m1 = order_m1["size"]
        order_side_m1 = order_m1["side"]

        # Protect API
        time.sleep(0.5)

        # Get order info for market 2
        order_m2 = await get_order(client, position["order_id_m2"])
        if order_m2 is None:
            print(f"Error: Order info for {position_market_m2} not found.")
            continue
        
        order_market_m2 = order_m2["ticker"]
        order_size_m2 = order_m2["size"]
        order_side_m2 = order_m2["side"]

        # Ensure sizes match what was sent to the exchange
        position_size_m1 = order_m1["size"]
        position_size_m2 = order_m2["size"]

        # Check if positions match exchange and live data
        check_m1 = position_market_m1 == order_market_m1 and position_size_m1 == order_size_m1 and position_side_m1 == order_side_m1
        check_m2 = position_market_m2 == order_market_m2 and position_size_m2 == order_size_m2 and position_side_m2 == order_side_m2
        check_live = position_market_m1 in markets_live and position_market_m2 in markets_live

        # Guard: If not all match exit with error
        if not check_m1 or not check_m2 or not check_live:
            print(f"Warning: Open positions for {position_market_m1} and {position_market_m2} do not match exchange records.")
            continue

        # Get price data
        series_1 = await get_candles_recent(client, position_market_m1)
        time.sleep(0.2)
        series_2 = await get_candles_recent(client, position_market_m2)
        time.sleep(0.2)

        # Get markets data for reference of tick size
        if position_market_m1 not in markets["markets"] or position_market_m2 not in markets["markets"]:
            print(f"Error: Market data not found for {position_market_m1} or {position_market_m2}")
            continue

        # Trigger close based on Z-Score if specified in constants
        if CLOSE_AT_ZSCORE_CROSS:
            hedge_ratio = position["hedge_ratio"]
            z_score_traded = position["z_score"]
            if len(series_1) > 0 and len(series_1) == len(series_2):
                spread = series_1 - (hedge_ratio * series_2)
                z_score_current = calculate_zscore(spread).values.tolist()[-1]

                # Determine if Z-score conditions trigger an exit
                z_score_level_check = abs(z_score_current) >= abs(z_score_traded)
                z_score_cross_check = (z_score_current < 0 and z_score_traded > 0) or (z_score_current > 0 and z_score_traded < 0)

                if z_score_level_check and z_score_cross_check:
                    is_close = True

        # Close positions if triggered
        if is_close:
            # Determine side for market 1
            side_m1 = "SELL" if position_side_m1 == "BUY" else "BUY"

            # Determine side for market 2
            side_m2 = "SELL" if position_side_m2 == "BUY" else "BUY"

            # Get and format Price
            price_m1 = float(series_1[-1])
            price_m2 = float(series_2[-1])
            tick_size_m1 = markets["markets"][position_market_m1]["tickSize"]
            tick_size_m2 = markets["markets"][position_market_m2]["tickSize"]
            accept_price_m1 = format_number(price_m1 * (1.05 if side_m1 == "BUY" else 0.99), tick_size_m1)
            accept_price_m2 = format_number(price_m2 * (1.05 if side_m2 == "BUY" else 0.99), tick_size_m2)

            # Close positions
            try:
                # Close position for market 1
                print(f"Closing position for {position_market_m1}")
                close_order_m1, order_id = await place_market_order(client, market=position_market_m1, side=side_m1, size=position_size_m1, price=accept_price_m1, reduce_only=True)
                print(f"Closed order for market 1: {close_order_m1['id']}")

                # Protect API
                time.sleep(1)

                # Close position for market 2
                print(f"Closing position for {position_market_m2}")
                close_order_m2, order_id = await place_market_order(client, market=position_market_m2, side=side_m2, size=position_size_m2, price=accept_price_m2, reduce_only=True)
                print(f"Closed order for market 2: {close_order_m2['id']}")

            except Exception as e:
                print(f"Error closing positions for {position_market_m1} and {position_market_m2}: {e}")
                save_output.append(position)
        else:
            save_output.append(position)

    # Save remaining positions
    print(f"{len(save_output)} positions remaining. Saving file...")
    with open("bot_agents.json", "w") as f:
        json.dump(save_output, f)
