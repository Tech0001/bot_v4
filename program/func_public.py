from constants import RESOLUTION
from func_utils import get_ISO_times
import pandas as pd
import numpy as np
import time

# Get relevant time periods for ISO from and to
ISO_TIMES = get_ISO_times()

# Retry mechanism for getting candles
async def get_candles_retry(client, market, retries=3, delay=1):
    """
    Retry fetching candles for a specific market.
    :param client: The DYDX client
    :param market: The market to fetch candles for
    :param retries: Number of retries to attempt
    :param delay: Time (in seconds) to wait between retries
    """
    for attempt in range(retries):
        try:
            response = await client.indexer.markets.get_perpetual_market_candles(
                market=market,
                resolution=RESOLUTION
            )
            return response["candles"]
        except Exception as e:
            print(f"Error fetching candles for {market}. Attempt {attempt + 1}/{retries}: {e}")
            time.sleep(delay)
    return None

# Get Recent Candles
async def get_candles_recent(client, market):
    close_prices = []
    time.sleep(0.2)

    # Retry fetching candles
    candles = await get_candles_retry(client, market)

    if candles:
        for candle in candles:
            close_prices.append(candle["close"])

        close_prices.reverse()
        prices_result = np.array(close_prices).astype(np.float64)
        return prices_result
    else:
        print(f"Failed to fetch recent candles for {market}")
        return None

# Get Historical Candles
async def get_candles_historical(client, market):
    close_prices = []
    for timeframe in ISO_TIMES.keys():
        tf_obj = ISO_TIMES[timeframe]
        from_iso = tf_obj["from_iso"] + ".000Z"
        to_iso = tf_obj["to_iso"] + ".000Z"

        time.sleep(0.2)
        candles = await get_candles_retry(client, market)

        if candles:
            for candle in candles:
                close_prices.append({"datetime": candle["startedAt"], market: candle["close"]})

    close_prices.reverse()
    return close_prices

# Get all available tradeable markets
async def get_markets(client):
    return await client.indexer.markets.get_perpetual_markets()

# Construct market prices dynamically for all tradeable markets
async def construct_market_prices(client):
    tradeable_markets = []
    markets = await get_markets(client)

    # Filter for active markets
    for market in markets["markets"].keys():
        market_info = markets["markets"][market]
        if market_info["status"] == "ACTIVE":
            tradeable_markets.append(market)

    # Fetch data for the first market to initialize the DataFrame
    close_prices = await get_candles_historical(client, tradeable_markets[0])
    if not close_prices:
        print(f"Failed to fetch historical data for {tradeable_markets[0]}")
        return None

    df = pd.DataFrame(close_prices)
    df.set_index("datetime", inplace=True)

    # Loop through the remaining markets to fetch their data
    for (i, market) in enumerate(tradeable_markets[1:], start=1):
        print(f"Extracting prices for {i + 1} of {len(tradeable_markets)} tokens for {market}")
        close_prices_add = await get_candles_historical(client, market)
        if close_prices_add:
            df_add = pd.DataFrame(close_prices_add)
            try:
                df_add.set_index("datetime", inplace=True)
                df = pd.merge(df, df_add, how="outer", on="datetime", copy=False)
            except Exception as e:
                print(f"Failed to add {market} - {e}")
            del df_add
        else:
            print(f"Failed to fetch data for {market}")

    # Drop columns with NaNs
    nans = df.columns[df.isna().any()].tolist()
    if nans:
        print(f"Dropping columns: {nans}")
        df.drop(columns=nans, inplace=True)

    return df
