from constants import ZSCORE_THRESH, USD_PER_TRADE, USD_MIN_COLLATERAL, MNEMONIC, DYDX_ADDRESS
from func_utils import format_number
from func_cointegration import calculate_zscore
from func_public import get_candles_recent, get_markets
from func_private import is_open_positions
from func_bot_agent import BotAgent
import pandas as pd
import json
from dydx_v4_client.wallet import Wallet
from dydx_v4_client.node.client import NodeClient
from dydx_v4_client.indexer.rest.indexer_client import IndexerClient
from dydx_v4_client.node.market import Market
from dydx_v4_client import MAX_CLIENT_ID, OrderFlags
from dydx_v4_client.indexer.rest.constants import OrderType
import random
import asyncio

from pprint import pprint

IGNORE_ASSETS = ["BTC-USD_x", "BTC-USD_y"]  # Ignore these assets which are not trading on testnet

async def place_market_order_v4(node_client, wallet, market_id, side, size):
    """
    Function to place a market order using the v4 structure.
    """
    # Initialize IndexerClient using node_client
    indexer = IndexerClient(node_client)

    # Fetch market data
    market_data = await indexer.markets.get_perpetual_markets(market_id)
    market = Market(market_data["markets"][market_id])

    # Generate the order ID and set the block height for the order
    order_id = market.order_id(wallet.address, 0, random.randint(0, MAX_CLIENT_ID), OrderFlags.SHORT_TERM)

    current_block = await node_client.latest_block_height()

    # Create the market order
    new_order = market.order(
        order_id=order_id,
        order_type=OrderType.MARKET,
        side=Market.Side.SIDE_BUY if side == "BUY" else Market.Side.SIDE_SELL,
        size=size,
        price=0,  # Market orders have a price of 0
        time_in_force=Market.TimeInForce.TIME_IN_FORCE_UNSPECIFIED,
        reduce_only=False,
        good_til_block=current_block + 10,
    )

    # Place the market order
    transaction = await node_client.place_order(wallet=wallet, order=new_order)
    wallet.sequence += 1
    return transaction


async def get_account_balance(indexer, address):
    """
    Retrieves account balance information for a given address using the correct API structure.
    """
    account_info = await indexer.get_account(address)
    
    # Properly handle the account response and check for balances
    if account_info and "balances" in account_info:
        free_collateral = float(account_info["balances"]["freeCollateral"])
        return free_collateral
    else:
        raise ValueError("Account balance information not found in account info.")


# Open positions function
async def open_positions(node_client):

    """
    Manage finding triggers for trade entry
    Store trades for managing later on for the exit function
    """

    # Load cointegrated pairs
    df = pd.read_csv("cointegrated_pairs.csv")

    # Get markets for reference (min order size, tick size, etc.)
    markets = await get_markets(node_client)

    # Initialize container for BotAgent results
    bot_agents = []

    # Open the JSON file containing open positions if it exists
    try:
        with open("bot_agents.json") as open_positions_file:
            open_positions_dict = json.load(open_positions_file)
            for p in open_positions_dict:
                bot_agents.append(p)
    except FileNotFoundError:
        bot_agents = []

    # Initialize the IndexerClient using the node_client's rest_indexer
    indexer = IndexerClient(node_client)

    # Loop through each row in the dataframe for trading opportunities
    for index, row in df.iterrows():

        # Extract variables
        base_market = row["base_market"]
        quote_market = row["quote_market"]
        hedge_ratio = row["hedge_ratio"]
        half_life = row["half_life"]

        # Continue if asset is in the ignore list
        if base_market in IGNORE_ASSETS or quote_market in IGNORE_ASSETS:
            continue

        # Get prices for base and quote markets
        try:
            series_1 = await get_candles_recent(node_client, base_market)
            series_2 = await get_candles_recent(node_client, quote_market)
        except Exception as e:
            print(e)
            continue

        # Calculate the ZScore
        if len(series_1) > 0 and len(series_1) == len(series_2):
            spread = series_1 - (hedge_ratio * series_2)
            z_score = calculate_zscore(spread).values.tolist()[-1]

            # Check if ZScore exceeds threshold
            if abs(z_score) >= ZSCORE_THRESH:

                # Ensure that no positions are already open for the base or quote markets
                is_base_open = await is_open_positions(node_client, base_market)
                is_quote_open = await is_open_positions(node_client, quote_market)

                # Proceed with trade placement if neither position is already open
                if not is_base_open and not is_quote_open:

                    # Determine buy/sell side based on ZScore
                    base_side = "BUY" if z_score < 0 else "SELL"
                    quote_side = "BUY" if z_score > 0 else "SELL"

                    # Get prices and format them according to tick sizes
                    base_price = series_1[-1]
                    quote_price = series_2[-1]
                    accept_base_price = float(base_price) * 1.01 if z_score < 0 else float(base_price) * 0.99
                    accept_quote_price = float(quote_price) * 1.01 if z_score > 0 else float(quote_price) * 0.99
                    base_tick_size = markets["markets"][base_market]["tickSize"]
                    quote_tick_size = markets["markets"][quote_market]["tickSize"]

                    # Format prices
                    accept_base_price = format_number(accept_base_price, base_tick_size)
                    accept_quote_price = format_number(accept_quote_price, quote_tick_size)

                    # Get size of trades based on USD_PER_TRADE
                    base_quantity = 1 / base_price * USD_PER_TRADE
                    quote_quantity = 1 / quote_price * USD_PER_TRADE
                    base_step_size = markets["markets"][base_market]["stepSize"]
                    quote_step_size = markets["markets"][quote_market]["stepSize"]

                    # Format sizes
                    base_size = format_number(base_quantity, base_step_size)
                    quote_size = format_number(quote_quantity, quote_step_size)

                    # Ensure the size is above the minimum order size
                    base_min_order_size = 1 / float(markets["markets"][base_market]["oraclePrice"])
                    quote_min_order_size = 1 / float(markets["markets"][quote_market]["oraclePrice"])

                    # Combine checks for order sizes
                    check_base = float(base_quantity) > base_min_order_size
                    check_quote = float(quote_quantity) > quote_min_order_size

                    # If checks pass, proceed with the trade
                    if check_base and check_quote:

                        # Get the account balance using the correct function
                        free_collateral = await get_account_balance(indexer, DYDX_ADDRESS)
                        print(f"Balance: {free_collateral} and minimum at {USD_MIN_COLLATERAL}")

                        # Ensure collateral is sufficient
                        if free_collateral < USD_MIN_COLLATERAL:
                            break

                        # Initialize wallet from mnemonic
                        wallet = await Wallet.from_mnemonic(node_client, MNEMONIC, DYDX_ADDRESS)

                        # Place Base Market Order
                        base_order_transaction = await place_market_order_v4(
                            node_client,
                            wallet,
                            market_id=base_market,
                            side=base_side,
                            size=base_size
                        )

                        # Place Quote Market Order
                        quote_order_transaction = await place_market_order_v4(
                            node_client,
                            wallet,
                            market_id=quote_market,
                            side=quote_side,
                            size=quote_size
                        )

                        # Print transaction details for debugging
                        print("Base Market Order Transaction:", base_order_transaction)
                        print("Quote Market Order Transaction:", quote_order_transaction)

                        # Create a BotAgent instance and store trades
                        bot_agent = BotAgent(
                            node_client,
                            market_1=base_market,
                            market_2=quote_market,
                            base_side=base_side,
                            base_size=base_size,
                            base_price=accept_base_price,
                            quote_side=quote_side,
                            quote_size=quote_size,
                            quote_price=accept_quote_price,
                            z_score=z_score,
                            half_life=half_life,
                            hedge_ratio=hedge_ratio
                        )

                        # Open trades with the BotAgent
                        bot_open_dict = await bot_agent.open_trades()

                        # Handle success or failure of the trade
                        if bot_open_dict == "failed":
                            continue

                        # If the trade is successful, store it in the list
                        if bot_open_dict["pair_status"] == "LIVE":
                            bot_agents.append(bot_open_dict)
                            del bot_open_dict

                            # Save trades to a JSON file
                            with open("bot_agents.json", "w") as f:
                                json.dump(bot_agents, f)

                            print("Trade status: Live")
                            print("---")

    # Save the final bot agents after the loop completes
    print(f"Success: Manage open trades checked")
