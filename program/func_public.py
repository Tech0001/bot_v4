from dydx_v4_client import MAX_CLIENT_ID, Order, OrderFlags
from dydx_v4_client.node.market import Market
from dydx_v4_client.indexer.rest.constants import OrderType
from constants import DYDX_ADDRESS, RESOLUTION
from func_utils import format_number, get_ISO_times
import random
import time
import numpy as np
import pandas as pd

ISO_TIMES = get_ISO_times()

# Get Recent Candles
async def get_candles_recent(client, market):
    close_prices = []
    time.sleep(0.2)  # Rate-limiting to avoid API overload
    response = await client.indexer.markets.get_perpetual_market_candles(
        market=market,
        resolution=RESOLUTION
    )
    candles = response["candles"]
    for candle in candles:
        close_prices.append(candle["close"])
    close_prices.reverse()  # Reverse to maintain chronological order
    return np.array(close_prices).astype(np.float64)

# Get Historical Candles
async def get_candles_historical(client, market):
    close_prices = []
    for timeframe in ISO_TIMES.keys():
        tf_obj = ISO_TIMES[timeframe]
        from_iso = tf_obj["from_iso"] + ".000Z"
        to_iso = tf_obj["to_iso"] + ".000Z"
        time.sleep(0.2)  # Rate-limiting for API
        response = await client.indexer.markets.get_perpetual_market_candles(
            market=market,
            resolution=RESOLUTION,
            from_iso=from_iso,
            to_iso=to_iso,
            limit=100
        )
        candles = response["candles"]
        for candle in candles:
            close_prices.append({"datetime": candle["startedAt"], market: candle["close"]})
    close_prices.reverse()
    return close_prices

# Fetch market prices directly for cointegration calculation
async def fetch_market_prices(client):
    try:
        # Fetch all markets data from the perpetual markets
        response = await client.indexer.markets.get_perpetual_markets()
        markets_data = response["markets"]

        # Initialize a dictionary to store close prices for each market
        prices_dict = {}

        # Fetch recent candles for each active market
        for market in markets_data:
            print(f"Fetching recent prices for market: {market}")
            prices = await get_candles_recent(client, market)

            # Ensure that the market has valid price data
            if prices is not None and len(prices) > 0:
                prices_dict[market] = prices
            else:
                print(f"Warning: No price data for market: {market}")

            # Adding rate-limiting between requests
            time.sleep(0.2)

        # Check if any markets have been added
        if not prices_dict:
            raise Exception("No market data fetched.")

        # Ensure all arrays are of the same length before constructing the DataFrame
        lengths = [len(prices) for prices in prices_dict.values()]
        min_length = min(lengths)
        if min_length == 0:
            raise Exception("One or more markets have no price data.")

        # Truncate arrays to the same minimum length
        for market in prices_dict.keys():
            prices_dict[market] = prices_dict[market][-min_length:]

        # Convert the prices dictionary into a DataFrame for easy manipulation
        df_market_prices = pd.DataFrame(prices_dict)

        # Drop any columns with NaN values (in case of mismatches)
        df_market_prices.dropna(axis=1, inplace=True)

        return df_market_prices

    except Exception as e:
        print(f"Error fetching market prices: {e}")
        return None

# Get Markets (missing in previous versions)
async def get_markets(client):
    try:
        # Fetch all perpetual markets
        response = await client.indexer.markets.get_perpetual_markets()
        return response["markets"]
    except Exception as e:
        print(f"Error fetching markets: {e}")
        return None

# Cancel Order
async def cancel_order(client, order_id):
    try:
        order = await get_order(client, order_id)
        ticker = order["ticker"]
        market = Market((await client.indexer.markets.get_perpetual_markets(ticker))["markets"][ticker])
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
        print(f"Attempted to cancel order for: {order['ticker']}. Please check the dashboard to ensure canceled.")
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

# Get Open Positions
async def get_open_positions(client):
    try:
        response = await client.indexer_account.account.get_subaccount(DYDX_ADDRESS, 0)
        return response["subaccount"]["openPerpetualPositions"]
    except Exception as e:
        print(f"Error fetching open positions: {e}")
        return {}

# Check if Positions are Open
async def is_open_positions(client, market):
    try:
        time.sleep(0.2)
        response = await client.indexer_account.account.get_subaccount(DYDX_ADDRESS, 0)
        open_positions = response["subaccount"]["openPerpetualPositions"]
        return market in open_positions.keys()
    except Exception as e:
        print(f"Error checking open positions for {market}: {e}")
        return False

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
