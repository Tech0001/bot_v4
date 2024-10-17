from dydx_v4_client import MAX_CLIENT_ID, Order, OrderFlags
from dydx_v4_client.node.market import Market
from dydx_v4_client.indexer.rest.constants import OrderType
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

# Place Market Order (enhanced logging)
async def place_market_order(client, market, side, size, price, reduce_only):
    try:
        size = float(size)
        price = float(price)

        # Log order parameters
        print(f"Placing order: Market={market}, Side={side}, Size={size}, Price={price}, ReduceOnly={reduce_only}")

        # Fetch and log subaccount details
        account = await get_account(client)
        print(f"Subaccount details: {account}")

        ticker = market
        current_block = await client.node.latest_block_height()
        market_data = (await client.indexer.markets.get_perpetual_markets(market))["markets"][market]
        print(f"Market data: {market_data}")

        market_instance = Market(market_data)
        market_order_id = market_instance.order_id(
            DYDX_ADDRESS, 0, random.randint(0, MAX_CLIENT_ID), OrderFlags.SHORT_TERM
        )

        # Set good_til_block to current_block + 20 (maximum allowed)
        good_til_block = current_block + 20

        # Set Order Type
        order_type = OrderType.MARKET

        # Set Time In Force to Immediate Or Cancel
        time_in_force = Order.TimeInForce.TIME_IN_FORCE_UNSPECIFIED

        # Place Market Order
        order_response = await client.node.place_order(
            client.wallet,
            market_instance.order(
                order_id=market_order_id,
                order_type=order_type,
                side=Order.Side.SIDE_BUY if side.upper() == "BUY" else Order.Side.SIDE_SELL,
                size=float(size),
                price=float(price),  # Set price to 0.0 for market orders
                time_in_force=time_in_force,
                reduce_only=reduce_only,
                good_til_block=good_til_block,
            ),
        )

        print("Order placement response:", order_response)

        # Check if the order was placed successfully
        if order_response and order_response.tx_response and order_response.tx_response.txhash:
            txhash = order_response.tx_response.txhash
            print("Order transaction hash:", txhash)
        else:
            print("Order response does not contain 'txhash'. Possible error:", order_response)
            return {"status": "failed", "error": "Order placement failed"}


        # Allow some time for the order to process
        time.sleep(2.5)

        # Fetch recent orders
        orders_response = await client.indexer_account.account.get_subaccount_orders(
            DYDX_ADDRESS,
            0,
            ticker,
            return_latest_orders="true",
        )

        # Initialize orders as an empty list if orders_response is None
        orders = []
        if orders_response is None:
            print("Error: Received None response for orders.")
            return {"status": "failed", "error": "No orders found"}
        
        # Check if orders_response is a list or dictionary
        if isinstance(orders_response, dict):
            orders = orders_response.get('orders', [])
        elif isinstance(orders_response, list):
            orders = orders_response
        else:
            raise ValueError("Unexpected response format for orders")

        # Debug: Print each order to understand its structure
        print("Recent orders fetched:")
        for order_item in orders:
            print("Order details:", order_item)

        # Find matching order ID
        order_id = next(
            (
                o["id"]
                for o in orders
                if int(o["clientId"]) == market_order_id.client_id
                and int(o["clobPairId"]) == market_order_id.clob_pair_id
            ),
            "",
        )

        if order_id == "":
            print("Order ID not found in recent orders. The order may have been immediately filled or canceled.")
            # Since market orders are Immediate or Cancel, they might not appear in open orders
            # You can try fetching filled orders or check the order status directly
            order_status = await check_order_status(client, market_order_id)
            print(f"Order status: {order_status}")
            if order_status != "FILLED":
                # Log detailed information about the order
                print(f"Order details: {order_response}")
                print(f"Market data: {market_data}")
                print(f"Order ID: {market_order_id}")
                raise ValueError("Order was not filled.")
            else:
                print("Order was filled successfully.")
                order_id = market_order_id  # Use the order ID for record-keeping

        else:
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
            data.append(
                {
                    "market": ticker,
                    "order_id": str(order_id),
                    "side": side,
                    "size": size,
                    "timestamp": time.time(),
                }
            )

            # Rewrite updated data to the file
            f.seek(0)
            json.dump(data, f, indent=4)
            f.truncate()  # Ensure the file is truncated if new data is shorter

        return {"status": "success", "order_id": str(order_id)}

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
