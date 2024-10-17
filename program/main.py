import asyncio
import time
import threading
import sys
from constants import ABORT_ALL_POSITIONS, FIND_COINTEGRATED, PLACE_TRADES, MANAGE_EXITS
from func_connections import connect_dydx
from func_private import abort_all_positions
from func_cointegration import store_cointegration_results
from func_exit_pairs import manage_trade_exits
from func_entry_pairs import open_positions
from func_messaging import send_message
from func_public import construct_market_prices  # Corrected import
import logging
from logging.handlers import RotatingFileHandler

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# Console handler
c_handler = logging.StreamHandler()
c_handler.setLevel(logging.DEBUG)

# File handler with rotation
f_handler = RotatingFileHandler('bot.log', maxBytes=5*1024*1024, backupCount=2)
f_handler.setLevel(logging.DEBUG)

# Formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
c_handler.setFormatter(formatter)
f_handler.setFormatter(formatter)

# Add handlers to the root logger
logger.addHandler(c_handler)
logger.addHandler(f_handler)


# Spinner function
def spinning_cursor():
    while True:
        for cursor in '|/-\\':
            yield cursor

def spinner_task():
    spinner = spinning_cursor()
    while True:
        sys.stdout.write(next(spinner))
        sys.stdout.flush()
        sys.stdout.write('\b')
        time.sleep(0.1)

def start_spinner():
    spinner_thread = threading.Thread(target=spinner_task)
    spinner_thread.daemon = True
    spinner_thread.start()

# MAIN FUNCTION
async def main():

    send_message("Bot launch successful")

    try:
        logger.info("Connecting to Client...")
        client, dydx_address, eth_address = await connect_dydx()
        if client is None:
            raise Exception("Failed to connect to client")
        logger.info("Connected to client successfully")
        logger.info(f"dYdX Address: {dydx_address}")
        logger.info(f"Ethereum Address: {eth_address}")
    except Exception as e:
        logger.info(f"Error connecting to client: {str(e)}")
        send_message(f"Failed to connect to client: {str(e)}")
        return  # Exit safely if connection fails

    if ABORT_ALL_POSITIONS:
        try:
            logger.info("Closing open positions...")
            await abort_all_positions(client)
            logger.info("All positions closed successfully")
        except Exception as e:
            logger.info(f"Error closing all positions: {str(e)}")
            send_message(f"Error closing all positions: {str(e)}")
            return  # Exit safely if position closure fails

    if FIND_COINTEGRATED:
        try:
            logger.info("Fetching token market prices...")
            # Removed hardcoded limit, now no limit unless provided in function call
            df_market_prices = await construct_market_prices(client)  # Fetch all markets by default
            if df_market_prices is None or len(df_market_prices) == 0:
                logger.info("Error: Market prices could not be fetched or the data is empty.")
                send_message("Error: Market prices could not be fetched or the data is empty.")
                return  # Exit safely if no market data
            logger.info("Market prices fetched successfully")
            logger.info(df_market_prices)  # Check the content of the data
        except Exception as e:
            logger.info(f"Error fetching market prices: {str(e)}")
            send_message(f"Error fetching market prices: {str(e)}")
            return  # Exit safely on market fetching error

        try:
            logger.info("Storing cointegrated pairs...")
            stores_result = store_cointegration_results(df_market_prices)
            if stores_result != "saved":
                logger.info(f"Error saving cointegrated pairs: {stores_result}")
                send_message(f"Error saving cointegrated pairs: {stores_result}")
                return  # Exit safely if saving fails
            logger.info("Cointegrated pairs stored successfully")
        except Exception as e:
            logger.info(f"Error saving cointegrated pairs: {str(e)}")
            send_message(f"Error saving cointegrated pairs: {str(e)}")
            return  # Exit safely on saving failure

    # Start the spinner
    start_spinner()

    # Main loop to manage exits and trades
    while True:
        if MANAGE_EXITS:
            try:
                logger.info("Managing exits...")
                await manage_trade_exits(client)
                logger.info("Exit management complete")
                time.sleep(1)  # Ensure API rate-limiting is handled
            except Exception as e:
                logger.info(f"Error managing exiting positions: {str(e)}")
                send_message(f"Error managing exiting positions: {str(e)}")
                return  # Exit safely or retry

        if PLACE_TRADES:
            try:
                logger.info("Finding trading opportunities...")
                await open_positions(client)
                logger.info("Trades placed successfully")
            except Exception as e:
                logger.info(f"Error trading pairs: {str(e)}")
                send_message(f"Error opening trades: {str(e)}")
                return  # Exit safely or retry

asyncio.run(main())
