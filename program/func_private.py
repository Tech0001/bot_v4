from dydx_v4_client import MAX_CLIENT_ID, Order, OrderFlags
from dydx_v4_client.node.market import Market
from dydx_v4_client.indexer.rest.constants import OrderType
from constants import DYDX_ADDRESS
from func_utils import format_number
from func_public import get_markets
import random
import time
import json

# Cancel Order
async def cancel_order(client, order_id):
    try:
        if order_id is None:
            raise ValueError("Invalid order_id: None")
        order = await get_order(client, order_id)
        market = Market((await client.indexer.markets.get_perpetual_markets(order["ticker"]))["markets"][order["ticker"]])
        market_order_id = market.order_id(DYDX_ADDRESS, 0, random.randint(0, MAX_CLIENT_ID), OrderFlags.SHORT_TERM)
        market_order_id.client_id = int(order["clientId"])
        market_order_id.clob_pair_id = int(order["clobPairId"])
        current_block = await client.node.latest_block_height()
        good_til_block = current_block + 1 + 10
        cancel = await client.node.cancel_order(
            client.wallet,
            market_order_id,
            good_til_block=good_til_block
        )
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

# Get Existing Order
async def get_order(client, order_id):
    try:
        if order_id is None:
            raise ValueError("Invalid order_id: None")
        order = await client.indexer_account.account.get_order(order_id)
        return order
    except Exception as e:
        print(f"Error fetching order details: {e}")
        return None

# Get existing open positions
async def is_open_positions(client, market):
    try:
        time.sleep(0.2)
        response = await client.indexer_account.account.get_subaccount(DYDX_ADDRESS, 0)
        open_positions = response["subaccount"]["openPerpetualPositions"]
        if len(open_positions) > 0:
            for token in open_positions.keys():
                if token == market:
                    return True
        return False
    except Exception as e:
        print(f"Error checking open positions: {e}")
        return False

# Check order status
async def check_order_status(client, order_id):
    try:
        order = await get_order(client, order_id)
        if order is None or "status" not in order:
            return "FAILED"
        return order["status"]
    except Exception as e:
        print(f"Error checking order status: {e}")
        return "FAILED"

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

        # New snippet integrated
        time.sleep(1.5)
        orders = await client.indexer_account.account.get_subaccount_orders(
            DYDX_ADDRESS, 0, ticker, return_latest_orders="true"
        )
        order_id = ""
        for order in orders:
            if int(order["clientId"]) == market_order_id.client_id and int(order["clobPairId"]) == market_order_id.clob_pair_id:
                order_id = order["id"]
                break

        if order_id == "":
            sorted_orders = sorted(orders, key=lambda x: x.get("createdAtHeight", 0), reverse=True)
            print("Warning: Unable to detect latest order. Order details:", sorted_orders)
            return None, None

        return order, order_id
    except Exception as e:
        print(f"Error placing market order: {e}")
        return None, None

# Cancel all orders
async def cancel_all_orders(client):
    try:
        orders = await client.indexer_account.account.get_subaccount_orders(DYDX_ADDRESS, 0, status="OPEN")
        if len(orders) > 0:
            for order in orders:
                await cancel_order(client, order["id"])
            print("Canceled open orders.")
    except Exception as e:
        print(f"Error canceling open orders: {e}")

# Abort all open positions
async def abort_all_positions(client):
    try:
        await cancel_all_orders(client)
        time.sleep(0.5)

        markets = await get_markets(client)
        time.sleep(0.5)

        positions = await get_open_positions(client)
        close_orders = []
        if len(positions) > 0:
            for item in positions.keys():
                pos = positions[item]
                market = pos["market"]
                side = "BUY" if pos["side"] == "SHORT" else "SELL"
                price = float(pos["entryPrice"])
                accept_price = price * 1.7 if side == "BUY" else price * 0.3
                tick_size = markets["markets"][market]["tickSize"]
                accept_price = format_number(accept_price, tick_size)

                order, order_id = await place_market_order(
                    client, market, side, pos["sumOpen"], accept_price, True
                )
                close_orders.append(order)
                time.sleep(0.2)

            bot_agents = []
            with open("bot_agents.json", "w") as f:
                json.dump(bot_agents, f)

        return close_orders
    except Exception as e:
        print(f"Error aborting all positions: {e}")
        return []
