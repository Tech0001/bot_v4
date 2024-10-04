from dydx_v4_client import MAX_CLIENT_ID, Order, OrderFlags
from dydx_v4_client.node.market import Market
from dydx_v4_client.indexer.rest.constants import OrderType
from constants import DYDX_ADDRESS
from func_utils import format_number
from func_public import get_markets
import random
import time
import json

# Retry count constant
MAX_RETRY_ATTEMPTS = 3
BACKOFF_DELAY = 2  # Backoff delay between retries

# Cancel Order
async def cancel_order(client, order_id):
    order = await get_order(client, order_id)
    ticker = order["ticker"]
    market = Market((await client.indexer.markets.get_perpetual_markets(ticker))["markets"][ticker])
    market_order_id = market.order_id(DYDX_ADDRESS, 0, random.randint(0, MAX_CLIENT_ID), OrderFlags.SHORT_TERM)
    current_block = await client.node.latest_block_height()
    good_til_block = current_block + 1 + 10
    cancel = await client.node.cancel_order(
        client.wallet,
        market_order_id,
        good_til_block=good_til_block
    )
    print(f"Attempted to cancel order for: {order['ticker']}. Please check the dashboard to ensure canceled.")

# Get Order
async def get_order(client, order_id):
    return await client.indexer_account.account.get_order(order_id)

# Get Account
async def get_account(client):
    account = await client.indexer_account.account.get_subaccount(DYDX_ADDRESS, 0)
    return account["subaccount"]

# Get Open Positions
async def get_open_positions(client):
    response = await client.indexer_account.account.get_subaccount(DYDX_ADDRESS, 0)
    return response["subaccount"]["openPerpetualPositions"]

# Check if Positions are Open
async def is_open_positions(client, market):
    time.sleep(0.2)
    response = await client.indexer_account.account.get_subaccount(DYDX_ADDRESS, 0)
    open_positions = response["subaccount"]["openPerpetualPositions"]
    if market in open_positions.keys():
        return True
    return False

# Place Market Order with Retry Logic and Backoff Strategy
async def place_market_order(client, ticker, side, size, price, reduce_only):
    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            current_block = await client.node.latest_block_height()
            market = Market((await client.indexer.markets.get_perpetual_markets(ticker))["markets"][ticker])
            market_order_id = market.order_id(DYDX_ADDRESS, 0, random.randint(0, MAX_CLIENT_ID), OrderFlags.SHORT_TERM)
            good_til_block = current_block + 1 + 10

            # Place Market Order
            order = await client.node.place_order(
                client.wallet,
                market.order(
                    market_order_id,
                    order_type=OrderType.MARKET,
                    side=Order.Side.SIDE_BUY if side == "BUY" else Order.Side.SIDE_SELL,
                    size=float(size),
                    price=float(price),
                    time_in_force=Order.TIME_IN_FORCE_UNSPECIFIED,
                    reduce_only=reduce_only,
                    good_til_block=good_til_block
                ),
            )

            # Check for a valid tx_response
            if hasattr(order, "tx_response"):
                if order.tx_response.raw_log == "[]":
                    raise ValueError("Transaction failed: Empty raw_log")
                return {"status": "success", "order_id": order.tx_response.txhash}
            else:
                raise ValueError("No tx_response found in order")

        except Exception as e:
            print(f"Error placing order attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS}: {e}")
            if attempt == MAX_RETRY_ATTEMPTS - 1:
                return {"status": "failed", "error": str(e)}

        # Wait before retrying
        print(f"Retrying after {BACKOFF_DELAY} seconds...")
        time.sleep(BACKOFF_DELAY)

# Cancel all open orders
async def cancel_all_orders(client):
    orders = await client.indexer_account.account.get_subaccount_orders(DYDX_ADDRESS, 0, status="OPEN")
    if len(orders) > 0:
        for order in orders:
            await cancel_order(client, order["id"])
            print(f"Order {order['id']} canceled.")

# Abort all open positions
async def abort_all_positions(client):
    # Cancel all orders
    await cancel_all_orders(client)
    
    # Get markets for reference of tick size
    markets = await get_markets(client)

    # Get all open positions
    positions = await get_open_positions(client)

    # Handle open positions
    if len(positions) > 0:
        for item in positions.keys():
            pos = positions[item]
            market = pos["market"]
            side = "BUY" if pos["side"] == "SHORT" else "SELL"
            price = float(pos["entryPrice"])
            accept_price = price * 1.7 if side == "BUY" else price * 0.3
            tick_size = markets["markets"][market]["tickSize"]
            accept_price = format_number(accept_price, tick_size)
            
            result = await place_market_order(client, market, side, pos["sumOpen"], accept_price, True)

            if result["status"] == "failed":
                print(f"Error closing position for {market}: {result['error']}")
                continue
            else:
                print(f"Closed position for {market}: {result['order_id']}")

        # Clear saved agents after aborting all positions
        with open("bot_agents.json", "w") as f:
            json.dump([], f)

# Check Order Status
async def check_order_status(client, order_id):
    order = await get_order(client, order_id)
    if "status" in order:
        return order["status"]
    return "UNKNOWN"
