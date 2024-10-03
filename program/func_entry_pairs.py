from constants import ZSCORE_THRESH, USD_PER_TRADE, USD_MIN_COLLATERAL, DYDX_ADDRESS, SECRET_PHRASE
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
from dydx_v4_client.network import TESTNET
import random

from pprint import pprint

IGNORE_ASSETS = ["BTC-USD_x", "BTC-USD_y"]

async def place_market_order_v4(node, wallet, market_id, side, size):
    """
    Updated function to place a market order using the v4 structure.
    """
    market = Market((await node.markets.get_perpetual_markets(market_id))["markets"][market_id])

    order_id = market.order_id(wallet.address, 0, random.randint(0, MAX_CLIENT_ID), OrderFlags.SHORT_TERM)

    current_block = await node.latest_block_height()

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

    transaction = await node.place_order(wallet=wallet, order=new_order)
    wallet.sequence += 1
    return transaction

async def get_account_balance_v4(node, wallet_address):
    """
    Fetch account balance using the v4 API structure via NodeClient.
    """
    # Fetch account details using the NodeClient
    account_info = await node.get_account(wallet_address)

    # Debug: Print out the entire account_info response
    print("Account Info Response: ", account_info)

    # Attempt to access the free collateral, or log if not found
    if hasattr(account_info, "free_collateral"):
        free_collateral = float(account_info.free_collateral)
    else:
        raise ValueError("free_collateral attribute not found in account_info")

    return free_collateral

# Open positions
async def open_positions(client):

    """
    Manage finding triggers for trade entry
    Store trades for managing later on for exit function
    """

    # Load cointegrated pairs
    df = pd.read_csv("cointegrated_pairs.csv")

    # Initialize NodeClient for TESTNET
    node = await NodeClient.connect(TESTNET.node)

    # Get markets for reference (min order size, tick size, etc.)
    markets = await get_markets(client)

    # Initialize container for BotAgent results
    bot_agents = []

    # Opening JSON file
    try:
        open_positions_file = open("bot_agents.json")
        open_positions_dict = json.load(open_positions_file)
        for p in open_positions_dict:
            bot_agents.append(p)
    except:
        bot_agents = []

    # Find ZScore triggers
    for index, row in df.iterrows():

        # Extract variables
        base_market = row["base_market"]
        quote_market = row["quote_market"]
        hedge_ratio = row["hedge_ratio"]
        half_life = row["half_life"]

        # Continue if asset is in the ignore list
        if base_market in IGNORE_ASSETS or quote_market in IGNORE_ASSETS:
            continue

        # Get prices
        try:
            series_1 = await get_candles_recent(client, base_market)
            series_2 = await get_candles_recent(client, quote_market)
        except Exception as e:
            print(e)
            continue

        # Get ZScore
        if len(series_1) > 0 and len(series_1) == len(series_2):
            spread = series_1 - (hedge_ratio * series_2)
            z_score = calculate_zscore(spread).values.tolist()[-1]

            # Establish if potential trade
            if abs(z_score) >= ZSCORE_THRESH:

                # Ensure like-for-like not already open (diversify trading)
                is_base_open = await is_open_positions(client, base_market)
                is_quote_open = await is_open_positions(client, quote_market)

                # Place trade
                if not is_base_open and not is_quote_open:

                    # Determine side
                    base_side = "BUY" if z_score < 0 else "SELL"
                    quote_side = "BUY" if z_score > 0 else "SELL"

                    # Get prices and format with tick sizes
                    base_price = series_1[-1]
                    quote_price = series_2[-1]
                    accept_base_price = float(base_price) * 1.01 if z_score < 0 else float(base_price) * 0.99
                    accept_quote_price = float(quote_price) * 1.01 if z_score > 0 else float(quote_price) * 0.99
                    base_tick_size = markets["markets"][base_market]["tickSize"]
                    quote_tick_size = markets["markets"][quote_market]["tickSize"]

                    # Format prices
                    accept_base_price = format_number(accept_base_price, base_tick_size)
                    accept_quote_price = format_number(accept_quote_price, quote_tick_size)

                    # Get size
                    base_quantity = 1 / base_price * USD_PER_TRADE
                    quote_quantity = 1 / quote_price * USD_PER_TRADE
                    base_step_size = markets["markets"][base_market]["stepSize"]
                    quote_step_size = markets["markets"][quote_market]["stepSize"]

                    # Format sizes
                    base_size = format_number(base_quantity, base_step_size)
                    quote_size = format_number(quote_quantity, quote_step_size)

                    # Ensure size (minimum order size > $1 according to V4 documentation)
                    base_min_order_size = 1 / float(markets["markets"][base_market]["oraclePrice"])
                    quote_min_order_size = 1 / float(markets["markets"][quote_market]["oraclePrice"])

                    # Combine checks
                    check_base = float(base_quantity) > base_min_order_size
                    check_quote = float(quote_quantity) > quote_min_order_size

                    # If checks pass, place trades
                    if check_base and check_quote:

                        # Wallet initialization (from mnemonic)
                        wallet = await Wallet.from_mnemonic(node, SECRET_PHRASE, DYDX_ADDRESS)

                        # Fetch account balance using NodeClient
                        free_collateral = await get_account_balance_v4(node, wallet.address)
                        print(f"Balance: {free_collateral} and minimum at {USD_MIN_COLLATERAL}")

                        # Guard: Ensure collateral
                        if free_collateral < USD_MIN_COLLATERAL:
                            break

                        # Place Base Market Order
                        base_order_transaction = await place_market_order_v4(
                            node,
                            wallet,
                            market_id=base_market,
                            side=base_side,
                            size=base_size
                        )

                        # Place Quote Market Order
                        quote_order_transaction = await place_market_order_v4(
                            node,
                            wallet,
                            market_id=quote_market,
                            side=quote_side,
                            size=quote_size
                        )

                        # Print transaction details for debugging
                        print("Base Market Order Transaction:", base_order_transaction)
                        print("Quote Market Order Transaction:", quote_order_transaction)

                        # Create Bot Agent
                        bot_agent = BotAgent(
                            client,
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

                        # Open trades
                        bot_open_dict = await bot_agent.open_trades()

                        # Guard: Handle failure
                        if bot_open_dict == "failed":
                            continue

                        # Handle success in opening trades
                        if bot_open_dict["pair_status"] == "LIVE":
                            # Append to list of bot agents
                            bot_agents.append(bot_open_dict)
                            del(bot_open_dict)

                            # Save trade
                            with open("bot_agents.json", "w") as f:
                                json.dump(bot_agents, f)

                            # Confirm live status
                            print("Trade status: Live")
                            print("---")

    # Save agents
    print(f"Success: Manage open trades checked")
