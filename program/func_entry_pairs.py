# Imports
import random
import time
import json
from dydx_v4_client import MAX_CLIENT_ID, Order, OrderFlags
from dydx_v4_client.node.market import Market
from dydx_v4_client.indexer.rest.constants import OrderType
from constants import DYDX_ADDRESS, ZSCORE_THRESH, USD_PER_TRADE, USD_MIN_COLLATERAL
from func_utils import format_number
from func_cointegration import calculate_zscore
from func_public import get_candles_recent, get_markets
from func_private import get_open_positions, get_account
from func_bot_agent import BotAgent
import pandas as pd
import asyncio

# Refine or remove IGNORE_ASSETS if not necessary
IGNORE_ASSETS = ["", ""]  # Example of assets you want to ignore

# Check if a position is open for a given market
async def is_open_positions(client, market):
    try:
        open_positions = await get_open_positions(client)

        # Ensure open_positions is a list or dictionary-like structure before processing
        if not isinstance(open_positions, (list, dict)):
            raise ValueError(f"Unexpected data format for open positions: {open_positions}")

        for position in open_positions:
            if isinstance(position, dict) and position.get("market") == market:
                return True
        return False
    except Exception as e:
        print(f"Error checking open positions for {market}: {e}")
        return False

# Improved Retry Logic with Exponential Backoff
async def fetch_order_with_retry(client, order_id, retries=3):
    retry_count = 0
    delay = 1  # Initial delay in seconds
    while retry_count < retries:
        try:
            order = await client.indexer_account.account.get_order(order_id)
            if 'createdAtHeight' in order:
                return order
            else:
                print(f"'createdAtHeight' not found. Retrying ({retry_count+1}/{retries})...")
        except Exception as e:
            print(f"Error fetching order: {e}")
        
        # Wait before retrying (exponential backoff)
        retry_count += 1
        await asyncio.sleep(delay)
        delay *= 2  # Increase delay with each retry
    
    print("Failed to fetch 'createdAtHeight' after retries. Proceeding without it.")
    return None

# Place market order
async def place_market_order(client, market, side, size, price, reduce_only):
    try:
        ticker = market
        current_block = await client.node.latest_block_height()
        market = Market((await client.indexer.markets.get_perpetual_markets(market))["markets"][market])
        market_order_id = market.order_id(DYDX_ADDRESS, 0, random.randint(0, MAX_CLIENT_ID), OrderFlags.SHORT_TERM)
        good_til_block = current_block + 1 + 10

        time_in_force = Order.TIME_IN_FORCE_UNSPECIFIED
        order = await client.node.place_order(
            client.wallet,
            market.order(
                market_order_id,
                order_type=OrderType.MARKET,
                side=Order.Side.SIDE_BUY if side == "BUY" else Order.Side.SIDE_SELL,
                size=float(size),
                price=float(price),
                time_in_force=time_in_force,
                reduce_only=reduce_only,
                good_til_block=good_til_block
            )
        )

        time.sleep(1.5)

        # Retrieve orders for the given ticker
        orders = await client.indexer_account.account.get_subaccount_orders(
            DYDX_ADDRESS, 0, ticker, return_latest_orders="true"
        )

        # Initialize order_id as empty
        order_id = None

        # Search for the matching order in the retrieved orders
        for order in orders:
            if int(order["clientId"]) == market_order_id.client_id and int(order["clobPairId"]) == market_order_id.clob_pair_id:
                order_id = order["id"]
                break

        # Check if 'createdAtHeight' is missing
        if 'createdAtHeight' not in order:
            print(f"Warning: 'createdAtHeight' not found after retries. Proceeding without it.")
            # Optionally log more detailed information here
            print(f"Full order data: {order}")

        # Check if order_id was not found
        if order_id is None:
            sorted_orders = sorted(orders, key=lambda x: x.get('createdAtHeight', 0), reverse=True)
            print("Warning: Unable to detect latest order. Order details:", sorted_orders)
            order_id = sorted_orders[0]["id"]  # Fallback: Use the first order from sorted list

        return order, order_id
    except Exception as e:
        print(f"Error placing market order: {e}")
        return None, None

# The rest of the code continues as normal
