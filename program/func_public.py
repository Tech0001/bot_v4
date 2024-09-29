from constants import RESOLUTION
from func_utils import get_ISO_times
import pandas as pd
import numpy as np
import time

# Get relevant time periods for ISO from and to
ISO_TIMES = get_ISO_times()

# Get Recent Candles
async def get_candles_recent(client, market):

    # Define output
    close_prices = []

    # Protect API
    time.sleep(0.2)

    try:
        # Get Prices from DYDX V4
        response = await client.indexer.markets.get_perpetual_market_candles(
            market=market,
            resolution=RESOLUTION
        )

        # Check response validity
        if "candles" not in response:
            print(f"Error: No candles found for market {market}")
            return np.array([])

        # Structure data
        for candle in response["candles"]:
            close_prices.append(candle["close"])

        # Construct and return close price series
        close_prices.reverse()
        return np.array(close_prices).astype(np.float64)

    except Exception as e:
        print(f"Error fetching candles for market {market}: {e}")
        return np.array([])

# Get Historical Candles
async def get_candles_historical(client, market):

    # Define output
    close_prices = []

    # Extract historical price data for each timeframe
    for timeframe in ISO_TIMES.keys():
        tf_obj = ISO_TIMES[timeframe]
        from_iso = tf_obj["from_iso"] + ".000Z"
        to_iso = tf_obj["to_iso"] + ".000Z"

        # Protect rate limits
        time.sleep(0.2)

        try:
            response = await client.indexer.markets.get_perpetual_market_candles(
                market=market,
                resolution=RESOLUTION,
                from_iso=from_iso,
                to_iso=to_iso,
                limit=100
            )

            if "candles" not in response:
                print(f"Error: No historical candles found for market {market} during {timeframe}")
                continue

            # Structure data
            for candle in response["candles"]:
                close_prices.append({"datetime": candle["startedAt"], market: candle["close"]})

        except Exception as e:
            print(f"Error fetching historical candles for market {market} during {timeframe}: {e}")
            continue

    # Construct and return DataFrame
    close_prices.reverse()
    return close_prices

# Get Markets
async def get_markets(client):
    try:
        return await client.indexer.markets.get_perpetual_markets()
    except Exception as e:
        print(f"Error fetching markets: {e}")
        return {}

# Construct market prices
async def construct_market_prices(client):

    # Ensure only Testnet Assets are used
    tradeable_markets = []
    markets = await get_markets(client)

    if "markets" not in markets:
        print("Error: Unable to fetch markets")
        return pd.DataFrame()  # Return empty DataFrame on failure

    # Find tradeable pairs
    for market in markets["markets"].keys():
        market_info = markets["markets"][market]
        if market_info["status"] == "ACTIVE":
            tradeable_markets.append(market)

    # Set initial DataFrame
    close_prices = await get_candles_historical(client, tradeable_markets[0])
    if len(close_prices) == 0:
        print("Error: No historical data found for the first market")
        return pd.DataFrame()  # Return empty DataFrame on failure

    df = pd.DataFrame(close_prices)
    df.set_index("datetime", inplace=True)

    # Append other prices to DataFrame
    for (i, market) in enumerate(tradeable_markets[1:]):  # Corrected to skip the first market
        print(f"Extracting prices for {i + 1} of {len(tradeable_markets)} tokens for {market}")
        close_prices_add = await get_candles_historical(client, market)
        if len(close_prices_add) == 0:
            print(f"Error: No data found for {market}, skipping...")
            continue

        df_add = pd.DataFrame(close_prices_add)
        try:
            df_add.set_index("datetime", inplace=True)
            df = pd.merge(df, df_add, how="outer", on="datetime", copy=False)
        except Exception as e:
            print(f"Failed to add {market} - {e}")
        del df_add

    # Check for columns with NaNs
    nans = df.columns[df.isna().any()].tolist()
    if len(nans) > 0:
        print(f"Dropping columns with NaNs: {nans}")
        df.drop(columns=nans, inplace=True)

    # Return result
    return df
