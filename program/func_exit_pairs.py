from constants import CLOSE_AT_ZSCORE_CROSS
from func_utils import format_number
from func_cointegration import calculate_zscore
from func_private import place_market_order, get_open_positions, get_order
from func_public import get_candles_recent, get_markets
import json
import time
import logging
logger = logging.getLogger(__name__)

# Manage trade exits
async def manage_trade_exits(client):
    """
    Manage exiting open positions based upon criteria set in constants.
    Handles both pair-based and single-market positions.
    """

    # Initialize saving output
    save_output = []

    # Open JSON file containing open positions
    try:
        with open("bot_agents.json", "r") as open_positions_file:
            open_positions_dict = json.load(open_positions_file)
    except FileNotFoundError:
        logger.info("Error: bot_agents.json not found")
        return "complete"

    # Guard: Exit if no open positions in file
    if len(open_positions_dict) < 1:
        logger.info("No open positions in bot_agents.json")
        return "complete"

    # Get all open positions from the trading platform
    exchange_pos = await get_open_positions(client)

    # Create live position tickers list
    markets_live = list(exchange_pos.keys())

    # Protect API rate limit
    time.sleep(0.5)

    # Iterate over all positions and process exits
    for position in open_positions_dict:
        # Check if the position is pair-based (market_1 and market_2) or single-market
        if "market_1" in position and "market_2" in position:
            # Pair-based position
            logger.info(f"Processing pair-based position: {position['market_1']}/{position['market_2']}")

            # Ensure the position has prices for market_1 and market_2
            if "price_m1" not in position or "price_m2" not in position:
                logger.info(f"Error: Missing price_m1 or price_m2 in position for {position['market_1']}/{position['market_2']}")
                continue  # Skip this position

            # Initialize close trigger
            is_close = False

            # Extract position information for market 1 and market 2
            position_market_m1 = position["market_1"]
            position_market_m2 = position["market_2"]
            original_price_m1 = float(position["price_m1"])
            original_price_m2 = float(position["price_m2"])

            # Get price data
            series_1 = await get_candles_recent(client, position_market_m1)
            series_2 = await get_candles_recent(client, position_market_m2)

            # Add logic to avoid selling at a loss
            current_price_m1 = float(series_1[-1])
            current_price_m2 = float(series_2[-1])

            if (position["order_m1_side"] == "BUY" and current_price_m1 < original_price_m1) or \
               (position["order_m2_side"] == "BUY" and current_price_m2 < original_price_m2):
                logger.info(f"Skipping exit: Selling {position_market_m1}/{position_market_m2} would result in a loss.")
                save_output.append(position)
                continue

            # Close positions if triggered by Z-Score
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
                # Determine side for market 1 and market 2
                side_m1 = "SELL" if position["order_m1_side"] == "BUY" else "BUY"
                side_m2 = "SELL" if position["order_m2_side"] == "BUY" else "BUY"

                # Fetch market data to get tick sizes
                markets = await get_markets(client)
                tick_size_m1 = markets["markets"][position_market_m1]["tickSize"]
                tick_size_m2 = markets["markets"][position_market_m2]["tickSize"]

                # Calculate acceptable close prices
                accept_price_m1 = format_number(current_price_m1 * (1.05 if side_m1 == "BUY" else 0.96), tick_size_m1)
                accept_price_m2 = format_number(current_price_m2 * (1.05 if side_m2 == "BUY" else 0.96), tick_size_m2)

                # Close positions
                try:
                    logger.info(f"Closing position for {position_market_m1}")
                    await place_market_order(client, market=position_market_m1, side=side_m1, size=position["order_m1_size"], price=accept_price_m1, reduce_only=True)

                    logger.info(f"Closing position for {position_market_m2}")
                    await place_market_order(client, market=position_market_m2, side=side_m2, size=position["order_m2_size"], price=accept_price_m2, reduce_only=True)

                except Exception as e:
                    logger.info(f"Error closing positions for {position_market_m1} and {position_market_m2}: {e}")
                    save_output.append(position)
            else:
                save_output.append(position)

        # Handle single-market positions if applicable (logic can be added here)
        elif "market" in position:
            logger.info(f"Processing single-market position: {position['market']}")
            # Single-market logic (if needed)
            save_output.append(position)

    # Save remaining positions
    logger.info(f"{len(save_output)} positions remaining. Saving file...")
    with open("bot_agents.json", "w") as f:
        json.dump(save_output, f)
