from dydx_v4_client import MAX_CLIENT_ID, Order, OrderFlags
from dydx_v4_client.node.market import Market
from dydx_v4_client.indexer.rest.constants import OrderType
from constants import DYDX_ADDRESS
from func_utils import format_number
from func_public import get_markets
import random
import time
import json

# Cancel all open orders
async def cancel_all_orders(client):
    try:
        # Fetch all open orders for the given subaccount
        orders = await client.indexer_account.account.get_subaccount_orders(
            DYDX_ADDRESS, 0, status="OPEN"
        )
        if len(orders) > 0:
            for order in orders:
                await cancel_order(client, order["id"])
            print("Canceled all open orders.")
        else:
            print("No open orders found.")
    except Exception as e:
        print(f"Error canceling all open orders: {e}")

# Cancel Order
async def cancel_order(client, order_id):
    try:
        if not order_id:
            raise ValueError("Invalid order_id: None")

        order = await get_order(client, order_id)
        if not order or "ticker" not in order:
            raise ValueError(f"Order data missing for order_id {order_id}.")

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
        print(f"Attempted to cancel order for: {order['ticker']}. Please check the dashboard to ensure it was canceled.")
    except Exception as e:
        print(f"Error canceling order: {e}")

# Get Account
async def get_account(client):
    try:
        account = await client.indexer_account.account.get_subaccount(DYDX_ADDRESS, 0)
        if not account or "subaccount" not in account:
            raise ValueError(f"Account data missing for {DYDX_ADDRESS}.")
        return account["subaccount"]
    except Exception as e:
        print(f"Error fetching account: {e}")
        return None

# Get Open Positions
async def get_open_positions(client):
    try:
        response = await client.indexer_account.account.get_subaccount(DYDX_ADDRESS, 0)
        if not response or "subaccount" not in response:
            raise ValueError(f"Open positions data is missing.")
        return response["subaccount"]["openPerpetualPositions"]
    except Exception as e:
        print(f"Error fetching open positions: {e}")
        return []

# Get Existing Order
async def get_order(client, order_id):
    try:
        if not order_id:
            raise ValueError("Invalid order_id: None")
        order = await client.indexer_account.account.get_order(order_id)
        if not order:
            raise ValueError(f"Order not found for order_id {order_id}")
        return order
    except Exception as e:
        print(f"Error fetching order details: {e}")
        return None

# Check order status
async def check_order_status(client, order_id):
    try:
        if not order_id:
            raise ValueError("Invalid order_id: None")
        order = await get_order(client, order_id)
        if not order or "status" not in order:
            raise ValueError(f"Order status could not be fetched for id {order_id}")
        return order["status"] if order["status"] else "FAILED"
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

        time.sleep(1.5)
        orders = await client.indexer_account.account.get_subaccount_orders(
            DYDX_ADDRESS, 0, ticker, return_latest_orders="true"
        )

        # Fallback logic for missing createdAtHeight
        order_id = None
        for order in orders:
            if int(order["clientId"]) == market_order_id.client_id and int(order["clobPairId"]) == market_order_id.clob_pair_id:
                order_id = order["id"]
                break

        # If we couldn't find order_id using clientId and clobPairId, sort by createdAt or createdAtHeight
        if not order_id:
            sorted_orders = sorted(orders, key=lambda x: x.get("createdAtHeight", x.get("createdAt", 0)), reverse=True)
            if sorted_orders:
                print("Warning: Using fallback for missing createdAtHeight. Latest order details:", sorted_orders[0])
                order_id = sorted_orders[0].get("id")

        if not order_id:
            print("Warning: Unable to detect latest order. Proceeding without order_id.")
            return None, None

        return order, order_id

    except Exception as e:
        print(f"Error placing market order: {e}")
        return None, None

# Abort all open positions
async def abort_all_positions(client):
    try:
        await cancel_all_orders(client)
        time.sleep(0.5)

        markets = await get_markets(client)
        time.sleep(0.5)

        positions = await get_open_positions(client)
        if not positions:
            print("No open positions to abort.")
            return []

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
                if not order:
                    print(f"Failed to place order to close position for {market}")
                    continue

                close_orders.append(order)
                time.sleep(0.2)

            bot_agents = []
            with open("bot_agents.json", "w") as f:
                json.dump(bot_agents, f)

        return close_orders
    except Exception as e:
        print(f"Error aborting all positions: {e}")
        return []
