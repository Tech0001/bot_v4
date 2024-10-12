import asyncio
from func_connections import connect_dydx

async def fetch_candlestick_data():
    client = await connect_dydx()
    market = "BTC-USD"  # Replace with your desired market
    resolution = "1HOUR"  # Adjust as needed: 1MIN, 4HOUR, 1DAY, etc.
    response = await client.indexer.markets.get_perpetual_candles(market, resolution)
    print(f"Candlestick Data: {response}")

asyncio.run(fetch_candlestick_data())
