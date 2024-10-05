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
from func_public import fetch_market_prices  # Corrected to match new version of func_public

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
        print("Connecting to Client...")
        client = await connect_dydx()
        print("Connected to client successfully")
    except Exception as e:
        print(f"Error connecting to client: {str(e)}")
        send_message(f"Failed to connect to client: {str(e)}")
        return  # Instead of exit, safely end the function

    if ABORT_ALL_POSITIONS:
        try:
            print("Closing open positions...")
            await abort_all_positions(client)
            print("All positions closed successfully")
        except Exception as e:
            print(f"Error closing all positions: {str(e)}")
            send_message(f"Error closing all positions: {str(e)}")
            return  # Exit gracefully

    if FIND_COINTEGRATED:
        try:
            print("Fetching token market prices...")
            df_market_prices = await fetch_market_prices(client)  # Use updated function
            if df_market_prices is None or len(df_market_prices) == 0:
                print("Error: Market prices could not be fetched or the data is empty.")
                send_message("Error: Market prices could not be fetched or the data is empty.")
                return  # Exit safely
            print("Market prices fetched successfully")
            print(df_market_prices)  # Check the content of the data (dictionary most likely)
        except Exception as e:
            print(f"Error fetching market prices: {str(e)}")
            send_message(f"Error fetching market prices: {str(e)}")
            return  # Exit safely

        try:
            print("Storing cointegrated pairs...")
            stores_result = store_cointegration_results(df_market_prices)
            if stores_result != "saved":
                print(f"Error saving cointegrated pairs: {stores_result}")
                send_message(f"Error saving cointegrated pairs: {stores_result}")
                return  # Exit safely
            print("Cointegrated pairs stored successfully")
        except Exception as e:
            print(f"Error saving cointegrated pairs: {str(e)}")
            send_message(f"Error saving cointegrated pairs: {str(e)}")
            return  # Exit safely

    # Start the spinner
    start_spinner()

    # Main loop to manage exits and trades
    while True:
        if MANAGE_EXITS:
            try:
                print("Managing exits...")
                await manage_trade_exits(client)
                print("Exit management complete")
                time.sleep(1)  # Ensure API rate-limiting is handled
            except Exception as e:
                print(f"Error managing exiting positions: {str(e)}")
                send_message(f"Error managing exiting positions: {str(e)}")
                return  # Exit safely, or consider retrying

        if PLACE_TRADES:
            try:
                print("Finding trading opportunities...")
                await open_positions(client)
                print("Trades placed successfully")
            except Exception as e:
                print(f"Error trading pairs: {str(e)}")
                send_message(f"Error opening trades: {str(e)}")
                return  # Exit safely, or consider retrying

asyncio.run(main())
