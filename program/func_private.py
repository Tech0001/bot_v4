from dydx_v4_client import MAX_CLIENT_ID, Order, OrderFlags
from dydx_v4_client.node.market import Market
from constants import DYDX_ADDRESS
from func_utils import format_number
import random
import time
import json

# Cancel Order
async def cancel_order(client, order_id):
    try:
        order = await get_order(client, order_id)
        if order is None:
            raise ValueError(f"Order {order_id} not found.")
        
        market = Market((await client.indexer.markets.get_perpetual_markets())["markets"][order["ticker"]])
        market_order_id = market.order_id(
            DYDX_ADDRESS,
            0,
            random.randint(0, MAX_CLIENT_ID),
            OrderFlags.SHORT_TERM
        )
        current_block = await client.node.latest_block_height()
        good_til_block = current_block + 1 + 10
        await client.node.cancel_order(
            client.wallet,
            market_order_id,
            good_til_block=good_til_block
        )
        print(f"Attempted to cancel order for: {order['ticker']}. Please check the dashboard to ensure it was canceled.")
    except Exception as e:
        print(f"Error canceling order: {e}")

# Get Order
async def get_order(client, order_id):
    try:
        return await client.indexer_account.account.get_order(order_id)
    except Exception as e:
        print(f"Error fetching order {order_id}: {e}")
        return None

# Get Account
async def get_account(client):
    try:
        account = await client.indexer_account.account.get_subaccount(DYDX_ADDRESS, 0)
        return account["subaccount"]
    except Exception as e:
        print(f"Error fetching account info: {e}")
        return None

# Get Account Balance
async def get_account_balance(client):
    try:
        account = await client.indexer_account.account.get_subaccount(DYDX_ADDRESS, 0)
        balance = account["subaccount"]["balance"]
        print(f"Account Balance: {balance}")
        return balance
    except Exception as e:
        print(f"Error fetching account balance: {e}")
        return None

# Get Open Positions
async def get_open_positions(client):
    try:
        response = await client.indexer_account.account.get_subaccount(DYDX_ADDRESS, 0)
        return response["subaccount"]["openPerpetualPositions"]
    except Exception as e:
        print(f"Error fetching open positions: {e}")
        return {}

# Place Market Order (with added delay)
async def place_market_order(client, market, side, size, price, reduce_only):
    try:
        size = float(size)
        price = float(price)

        ticker = market
        current_block = await client.node.latest_block_height()
        market_data = (await client.indexer.markets.get_perpetual_markets())["markets"][ticker]
        market = Market(market_data)
        market_order_id = market.order_id(DYDX_ADDRESS, 0, random.randint(0, MAX_CLIENT_ID), OrderFlags.SHORT_TERM)
        good_til_block = current_block + 1 + 10

        # Place Market Order
        order = await client.node.place_order(
            client.wallet,
            market.order(
                market_order_id,
                side=Order.Side.SIDE_BUY if side == "BUY" else Order.Side.SIDE_SELL,
                size=size,
                price=price,
                time_in_force=Order.TIME_IN_FORCE_UNSPECIFIED,
                reduce_only=reduce_only,
                good_til_block=good_til_block
            ),
        )

        # Add a delay before fetching recent orders to allow time for the order to be fully registered
        time.sleep(5)  # Introduce a 5-second delay here

        # Confirm recent order placement
        orders = await client.indexer_account.account.get_subaccount_orders(
            DYDX_ADDRESS,
            0,
            ticker,
            return_latest_orders="true",
        )

        # Find matching order ID
        order_id = next(
            (o["id"] for o in orders if int(o["clientId"]) == market_order_id.client_id and int(o["clobPairId"]) == market_order_id.clob_pair_id),
            ""
        )

        if order_id == "":
            raise ValueError("Order placement failed: Unable to detect order in recent orders")

        print(f"Order placed successfully: {order_id}")
        
        # Update the bot_agents.json file after successful order placement
        with open("bot_agents.json", "r+") as f:
            try:
                # Load existing data
                data = json.load(f)
            except json.JSONDecodeError:
                # If file is empty or corrupt, start with an empty list
                data = []
            
            # Add new order data
            data.append({
                "market": ticker,  # Use the ticker string for serialization
                "order_id": order_id,
                "side": side,
                "size": size,
                "price": price,
                "timestamp": time.time()
            })

            # Rewrite updated data to the file
            f.seek(0)
            json.dump(data, f, indent=4)
            f.truncate()  # Ensure the file is truncated if new data is shorter

        return {"status": "success", "order_id": order_id}

    except Exception as e:
        print(f"Error placing order: {e}")
        return {"status": "failed", "error": str(e)}

# Cancel All Open Orders
async def cancel_all_orders(client):
    try:
        orders = await client.indexer_account.account.get_subaccount_orders(DYDX_ADDRESS, 0, status="OPEN")
        if len(orders) > 0:
            for order in orders:
                await cancel_order(client, order["id"])
                print(f"Order {order['id']} canceled.")
        else:
            print("No open orders found.")
    except Exception as e:
        print(f"Error canceling open orders: {e}")

# Abort All Open Positions
async def abort_all_positions(client):
    try:
        # Cancel all open orders
        await cancel_all_orders(client)

        # Fetch all available markets
        markets_response = await client.indexer.markets.get_perpetual_markets()
        if not markets_response or "markets" not in markets_response:
            raise ValueError("Markets data is missing or invalid.")
        markets = markets_response["markets"]

        # Fetch all open positions
        positions = await get_open_positions(client)

        if len(positions) > 0:
            for item in positions.keys():
                pos = positions[item]
                market = pos["market"]
                side = "BUY" if pos["side"] == "SHORT" else "SELL"
                price = float(pos["entryPrice"])

                # Ensure market exists
                if market not in markets:
                    print(f"Market data for {market} not found.")
                    continue

                tick_size = markets[market]["tickSize"]
                accept_price = price * 1.7 if side == "BUY" else price * 0.3  # Ensure order fills
                accept_price = format_number(accept_price, tick_size)

                # Place market order to close position
                result = await place_market_order(client, market, side, pos["sumOpen"], accept_price, True)

                if result["status"] == "failed":
                    print(f"Error closing position for {market}: {result['error']}")
                else:
                    print(f"Closed position for {market}: {result['order_id']}")

            # Clear saved agents after aborting all positions
            with open("bot_agents.json", "w") as f:
                json.dump([], f)  # Only clears the file after successful closing of positions.
        else:
            print("No open positions found.")
    except Exception as e:
        print(f"Error aborting all positions: {e}")

# Check Order Status
async def check_order_status(client, order_id):
    try:
        if order_id:  # Ensure order_id is valid and not None
            order = await get_order(client, order_id)
            if "status" in order:
                return order["status"]
            else:
                raise ValueError(f"Order status not found for order ID: {order_id}")
        else:
            raise ValueError("Invalid order_id provided")
    except Exception as e:
        print(f"Error checking order status for {order_id}: {e}")
        return "UNKNOWN"
