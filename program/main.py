import asyncio
import itertools  # For the spinner functionality
import sys  # For printing spinner output
import time
from constants import ABORT_ALL_POSITIONS, FIND_COINTEGRATED, PLACE_TRADES, MANAGE_EXITS
from func_connections import connect_dydx
from func_private import abort_all_positions, get_open_positions
from func_public import construct_market_prices
from func_cointegration import store_cointegration_results
from func_exit_pairs import manage_trade_exits
from func_messaging import send_message
from func_entry_pairs import open_positions  # Import only what is needed

# Spinner function to indicate the bot is working
async def spinner_task():
    spinner = itertools.cycle(['%', '%%', '%%%'])
    while True:
        sys.stdout.write(next(spinner))
        sys.stdout.flush()
        sys.stdout.write('\b\b\b')  # Backspace to clear spinner symbols
        await asyncio.sleep(0.1)

# MAIN FUNCTION
async def main():

    # Send a message on bot launch
    send_message("Bot launch successful")

    # Connect to client
    try:
        print("\nProgram started...")
        print("Connecting to Client...")
        client = await connect_dydx()  # Connect to the client
    except Exception as e:
        print("Error connecting to client: ", e)
        send_message(f"Failed to connect to client {e}")
        exit(1)

    # Abort all open positions if the flag is set
    if ABORT_ALL_POSITIONS:
        try:
            print("\nClosing open positions...")
            await abort_all_positions(client)
            print("Finished closing open positions.")
        except Exception as e:
            print("Error closing all positions: ", e)
            send_message(f"Error closing all positions {e}")
            exit(1)

    # Find Cointegrated Pairs if the flag is set
    if FIND_COINTEGRATED:
        try:
            print("\nFetching token market prices, please allow around 5 minutes...")
            df_market_prices = await construct_market_prices(client)
            print(df_market_prices)
        except Exception as e:
            print("Error constructing market prices: ", e)
            send_message(f"Error constructing market prices {e}")
            exit(1)

        try:
            print("\nStoring cointegrated pairs...")
            stores_result = store_cointegration_results(df_market_prices)
            if stores_result != "saved":
                print("Error saving cointegrated pairs")
                exit(1)
        except Exception as e:
            print("Error saving cointegrated pairs: ", e)
            send_message(f"Error saving cointegrated pairs {e}")
            exit(1)

    # Run bot operations in an always-on loop
    while True:

        # Start spinner task to show it's actively looking for trades
        spinner = asyncio.create_task(spinner_task())  # Start the spinner

        # Manage existing positions
        if MANAGE_EXITS:
            try:
                print("\nManaging exits...")
                await manage_trade_exits(client)  # Manage trade exits
                print("Finished managing exits.")
                await asyncio.sleep(1)
            except Exception as e:
                print("Error managing exiting positions: ", e)
                send_message(f"Error managing exiting positions {e}")
                exit(1)

        # Place trades for opening positions
        if PLACE_TRADES:
            try:
                print("\nFinding trading opportunities...")
                await open_positions(client)  # Your bot's main logic
                await asyncio.sleep(1)
            except Exception as e:
                print("Error trading pairs: ", e)
                send_message(f"Error opening trades {e}")
                exit(1)

        # Cancel the spinner when any activity happens (trades or exits)
        spinner.cancel()
        print("\n")

        # Pause briefly before starting the next iteration
        await asyncio.sleep(1)


# Run the main function with asyncio
asyncio.run(main())
