import asyncio
from func_connections import connect_dydx
import logging
logger = logging.getLogger(__name__)

async def fetch_candlestick_data():
    client, dydx_address, eth_address = await connect_dydx()  # Ensure correct unpacking
    market = "BTC-USD"  # Replace with your desired market
    resolution = "1HOUR"  # Adjust as needed: 1MIN, 4HOUR, 1DAY, etc.
    # Use the correct method to fetch market data
    response = await client.indexer.markets.get_perpetual_markets()
    
    # Process the response as needed
    # For example, extract the specific market data you need
    market_data = response["markets"].get(market)
    if market_data:
        logger.info(f"Market data for {market}: {market_data}")
    else:
        logger.info(f"Market {market} not found.")

asyncio.run(fetch_candlestick_data())
