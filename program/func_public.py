from dydx_v4_client import MAX_CLIENT_ID, Order, OrderFlags
from dydx_v4_client.node.market import Market
from dydx_v4_client.indexer.rest.constants import OrderType
from constants import DYDX_ADDRESS, RESOLUTION
from func_utils import format_number, get_ISO_times
import random
import time
import json
import numpy as np
import pandas as pd

ISO_TIMES = get_ISO_times()

# Fetch market prices directly for cointegration calculation
async def fetch_market_prices(client):
    try:
        response = await client.indexer.markets.get_perpetual_markets()
        markets_data = response["markets"]

        # Extract close prices from market data for each asset
        prices_dict = {}
        for market in markets_data:
            prices_dict[market] = await get_candles_recent(client, market)

        # Convert the prices dictionary into a DataFrame for easy manipulation
        df_market_prices = pd.DataFrame(prices_dict)
        return df_market_prices

    except Exception as e:
        print(f"Error fetching market prices: {e}")
        return None

# Cancel Order
async def cancel_order(client, order_id):
    order = await get_order(client, order_id)
    ticker = order["ticker"]
    market = Market((await client.indexer.markets.get_perpetual_markets(ticker))["markets"][ticker])
    market_order_id = market.order_id(DYDX_ADDRESS, 0, random.randint(0, MAX_CLIENT_ID), OrderFlags.SHORT_TERM)
    current_block = await client.node.latest_block_height()
    good_til_block = current_block + 1 + 10
    await client.node.cancel_order(
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
    return market in open_positions.keys()

# Place Market Order
async def place_market_order(client, market, side, size, price, reduce_only):
    try:
        # Ensure values are floats for comparison
        size = float(size)
        price = float(price)

        ticker = market
        current_block = await client.node.latest_block_height()
        market = Market((await client.indexer.markets.get_perpetual_markets(market))["markets"][market])
        market_order_id = market.order_id(DYDX_ADDRESS, 0, random.randint(0, MAX_CLIENT_ID), OrderFlags.SHORT_TERM)
        good_til_block = current_block + 1 + 10

        # Place Market Order
        order = await client.node.place_order(
            client.wallet,
            market.order(
                market_order_id,
                order_type=OrderType.MARKET,
                side=Order.Side.SIDE_BUY if side == "BUY" else Order.Side.SIDE_SELL,
                size=size,
                price=price,
                time_in_force=Order.TIME_IN_FORCE_UNSPECIFIED,
                reduce_only=reduce_only,
                good_til_block=good_til_block
            ),
        )

        return order

    except Exception as e:
        print(f"Error placing market order: {e}")
        return None

# Get Recent Candles
async def get_candles_recent(client, market):
    close_prices = []
    time.sleep(0.2)
    response = await client.indexer.markets.get_perpetual_market_candles(
        market=market,
        resolution=RESOLUTION
    )
    candles = response
    for candle in candles["candles"]:
        close_prices.append(candle["close"])
    close_prices.reverse()
    return np.array(close_prices).astype(np.float64)

# Get Historical Candles
async def get_candles_historical(client, market):
    close_prices = []
    for timeframe in ISO_TIMES.keys():
        tf_obj = ISO_TIMES[timeframe]
        from_iso = tf_obj["from_iso"] + ".000Z"
        to_iso = tf_obj["to_iso"] + ".000Z"
        time.sleep(0.2)
        response = await client.indexer.markets.get_perpetual_market_candles(
            market=market,
            resolution=RESOLUTION,
            from_iso=from_iso,
            to_iso=to_iso,
            limit=100
        )
        candles = response
        for candle in candles["candles"]:
            close_prices.append({"datetime": candle["startedAt"], market: candle["close"]})
    close_prices.reverse()
    return close_prices
