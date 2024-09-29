from dydx_v4_client import MAX_CLIENT_ID, Order, OrderFlags
from dydx_v4_client.node.market import Market
from dydx_v4_client.indexer.rest.constants import OrderType
from constants import DYDX_ADDRESS
from func_utils import format_number
from func_public import get_markets
import random
import time
import json
from datetime import datetime

# Cancel Order
async def cancel_order(client, order_id):
    try:
        # Ensure order details exist
        order = await client.indexer_account.account.get_order(order_id)
        market = Market((await client.indexer.markets.get_perpetual_markets(order["ticker"]))["markets"][order["ticker"]])
        market_order_id = market.order_id(DYDX_ADDRESS, 0, random.randint(0, MAX_CLIENT_ID), OrderFlags.SHORT_TERM)
        current_block = await client.node.latest_block_height()
        good_til_block = current_block + 1 + 10
        cancel = await client.node.cancel_order(
            client.wallet,
            market_order_id,
            good_til_block=good_til_block
        )
        print(cancel)
        print(f"Attempted to cancel order for: {order['ticker']}. Please check dashboard to ensure cancelled.")
    except Exception as e:
        print(f"Error canceling order: {e}")

# Get Account
async def get_account(client):
    try:
        account = await client.indexer_account.account.get_subaccount(DYDX_ADDRESS, 0)
        return account["subaccount"]
    except Exception as e:
        print(f"Error fetching account: {e}")
        return None

# Get Open Positions
async def get_open_positions(client):
    try:
        response = await client.indexer_account.account.get_subaccount(DYDX_ADDRESS, 0)
        return response["subaccount"]["openPerpetualPositions"]
    except Exception as e:
        print(f"Error fetching open positions: {e}")
        return []

# Check order status
async def check_order_status(client, order_id):
    try:
        order = await client.indexer_account.account.get_order(order_id)
        if order["status"]:
            return order["status"]
        return "FAILED"
    except Exception as e:
        print(f"Error checking order status: {e}")
        return "FAILED"

# Place market order
async def place_market_order(client, market, side, size, price, reduce_only):
    try:
        print(f"Placing trade for market: {market}, side: {side}, size: {size}")

        ticker = market
        current_block = await client.node.latest_block_height()
        market = Market((await client.indexer.markets.get_perpetual_markets(market))["markets"][market])
        market_order_id = market.order_id(DYDX_ADDRESS, 0, random.randint(0, MAX_CLIENT_ID), OrderFlags.SHORT_TERM)
        good_til_block = current_block + 1 + 10

        # Set time in force
        time_in_force = Order.TIME_IN_FORCE_UNSPECIFIED

        # Place Market Order
        order = await client.node.place_order(
            client.wallet,
            market.order(
                market_order_id,
                order_type=OrderType.MARKET,
                side=Order.Side.SIDE_BUY if side == "BUY" else Order.Side.SIDE_SELL,
                size=float(size),
                price=float(price) if price else "0",  # Use "0" for market orders
                time_in_force=time_in_force,
                reduce_only=reduce_only,
                good_til_block=good_til_block
            )
        )
        print(f"Order placed: {order}")
        return order, market_order_id
    except Exception as e:
        print(f"Error placing market order: {e}")
        return None, None

# Get Existing Order
async def get_order(client, order_id):
    """
    Function to retrieve an order by order_id.
    """
    try:
        order = await client.indexer_account.account.get_order(order_id)
        return order
    except Exception as e:
        print(f"Error fetching order details: {e}")
        return None

# Abort all open positions
async def abort_all_positions(client):
    try:
        # Fetch all open positions
        open_positions = await get_open_positions(client)

        if len(open_positions) > 0:
            for position in open_positions:
                market = position['market']
                size = position['size']
                side = "SELL" if position['side'] == "BUY" else "BUY"

                # Close the position
                await place_market_order(client, market, side, size, price=None, reduce_only=True)
                print(f"Closed position for market: {market}")
    except Exception as e:
        print(f"Error aborting positions: {e}")
