import asyncio
import time
from constants import ABORT_ALL_POSITIONS, FIND_COINTEGRATED, PLACE_TRADES, MANAGE_EXITS
from func_connections import connect_dydx
from func_private import abort_all_positions
from func_public import construct_market_prices
from func_cointegration import store_cointegration_results
from func_exit_pairs import manage_trade_exits
from func_entry_pairs import open_positions
from func_messaging import send_message

async def main():

    # Send message on bot launch
    send_message("Bot launch successful")

    # Connect to client
    try:
        print("\nProgram started...")
        print("Connecting to Client...")
        client = await connect_dydx()
    except Exception as e:
        print("Error connecting to client: ", e)
        send_message(f"Failed to connect to client {e}")
        exit(1)

    # Abort all open positions if flag is set
    if ABORT_ALL_POSITIONS:
        try:
            print("\nClosing open positions...")
            await abort_all_positions(client)
            print("Finished closing open positions.")
        except Exception as e:
            print("Error closing all positions: ", e)
            send_message(f"Error closing all positions {e}")
            exit(1)

    # Find Cointegrated Pairs if flag is set
    if FIND_COINTEGRATED:
        try:
            print("\nFetching token market prices...")
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
        # Manage existing positions
        if MANAGE_EXITS:
            try:
                print("\nManaging exits...")
                await manage_trade_exits(client)
                print("Finished managing exits.")
                await asyncio.sleep(1)
            except Exception as e:
                print("Error managing exits: ", e)
                send_message(f"Error managing exits {e}")
                exit(1)

        # Place trades for opening positions
        if PLACE_TRADES:
            try:
                print("\nFinding trading opportunities...")
                await open_positions(client)
                await asyncio.sleep(1)
            except Exception as e:
                print("Error trading pairs: ", e)
                send_message(f"Error opening trades {e}")
                exit(1)

        # Pause before next iteration
        await asyncio.sleep(1)

asyncio.run(main())
