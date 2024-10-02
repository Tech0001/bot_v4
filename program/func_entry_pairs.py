# Imports
import random
import time
import json
from dydx_v4_client import MAX_CLIENT_ID, Order, OrderFlags
from dydx_v4_client.node.market import Market
from dydx_v4_client.indexer.rest.constants import OrderType
from dydx_v4_client.indexer.rest.indexer_client import IndexerClient
from dydx_v4_client.network import TESTNET
from constants import DYDX_ADDRESS, ZSCORE_THRESH, USD_PER_TRADE, USD_MIN_COLLATERAL
from func_utils import format_number
from func_cointegration import calculate_zscore
from func_public import get_candles_recent, get_markets
from func_private import get_open_positions, get_account
from func_bot_agent import BotAgent
import pandas as pd
import asyncio

# Refine or remove IGNORE_ASSETS if not necessary
IGNORE_ASSETS = ["", ""]  # Example of assets you want to ignore

# Check if a position is open for a given market
async def is_open_positions(client, market):
    try:
        open_positions = await get_open_positions(client)

        # Ensure open_positions is a list or dictionary-like structure before processing
        if not isinstance(open_positions, (list, dict)):
            raise ValueError(f"Unexpected data format for open positions: {open_positions}")

        for position in open_positions:
            if isinstance(position, dict) and position.get("market") == market:
                return True
        return False
    except Exception as e:
        print(f"Error checking open positions for {market}: {e}")
        return False

# Fetch perpetual market data
async def fetch_market_data(client, market):
    try:
        # Get market details for the given market
        response = await client.markets.get_perpetual_markets(market=market)
        market_data = response["markets"][market]
        return market_data
    except Exception as e:
        print(f"Error fetching market data for {market}: {e}")
        return None

# Place market order
async def place_market_order(client, market, side, size, price, reduce_only):
    try:
        ticker = market
        current_block = await client.node.latest_block_height()
        market = Market((await client.indexer.markets.get_perpetual_markets(market))["markets"][market])
        market_order_id = market.order_id(DYDX_ADDRESS, 0, random.randint(0, MAX_CLIENT_ID), OrderFlags.SHORT_TERM)
        good_til_block = current_block + 1 + 10

        time_in_force = Order.TIME_IN_FORCE_UNSPECIFIED
        order = await client.node.place_order(
            client.wallet,
            market.order(
                market_order_id,
                order_type=OrderType.MARKET,
                side=Order.Side.SIDE_BUY if side == "BUY" else Order.Side.SIDE_SELL,
                size=float(size),
                price=float(price),
                time_in_force=time_in_force,
                reduce_only=reduce_only,
                good_til_block=good_til_block
            )
        )

        time.sleep(1.5)

        # Retrieve orders for the given ticker
        orders = await client.indexer_account.account.get_subaccount_orders(
            DYDX_ADDRESS, 0, ticker, return_latest_orders="true"
        )

        # Initialize order_id as empty
        order_id = None

        # Search for the matching order in the retrieved orders
        for order in orders:
            if int(order["clientId"]) == market_order_id.client_id and int(order["clobPairId"]) == market_order_id.clob_pair_id:
                order_id = order["id"]
                break

        # Check if order_id was not found
        if order_id is None:
            sorted_orders = sorted(orders, key=lambda x: x.get("createdAtHeight", 0), reverse=True)
            print("Warning: Unable to detect latest order. Order details:", sorted_orders)
            order_id = sorted_orders[0]["id"]  # Fallback: Use the first order from sorted list

        return order, order_id
    except Exception as e:
        print(f"Error placing market order: {e}")
        return None, None

# Open positions function - manage finding triggers for trade entry
async def open_positions(client):
    """
    Manage finding triggers for trade entry
    Store trades for managing later on in the exit function
    """

    # Load cointegrated pairs
    df = pd.read_csv("cointegrated_pairs.csv")

    # Initialize IndexerClient for fetching market data
    client = IndexerClient(TESTNET.rest_indexer)

    # Initialize container for BotAgent results
    bot_agents = []

    # Open JSON file and load existing bot agents
    try:
        with open("bot_agents.json") as open_positions_file:
            open_positions_dict = json.load(open_positions_file)
            for p in open_positions_dict:
                bot_agents.append(p)
    except FileNotFoundError:
        bot_agents = []

    # Iterate through cointegrated pairs
    for index, row in df.iterrows():
        base_market = row["base_market"]
        quote_market = row["quote_market"]
        hedge_ratio = row["hedge_ratio"]
        half_life = row["half_life"]

        # Skip ignored assets
        if base_market in IGNORE_ASSETS or quote_market in IGNORE_ASSETS:
            print(f"Skipping ignored asset pair: {base_market} - {quote_market}")
            continue

        # Log to ensure BTC-USD is being processed
        if base_market == "BTC-USD" or quote_market == "BTC-USD":
            print(f"Processing BTC-USD pair: {base_market} - {quote_market}")

        # Fetch market data
        try:
            base_market_data = await fetch_market_data(client, base_market)
            quote_market_data = await fetch_market_data(client, quote_market)
        except Exception as e:
            print(f"Error fetching data for {base_market} or {quote_market}: {e}")
            continue

        # Get recent prices
        try:
            series_1 = await get_candles_recent(client, base_market)
            series_2 = await get_candles_recent(client, quote_market)
        except Exception as e:
            print(f"Error fetching candle data for {base_market} or {quote_market}: {e}")
            continue

        # Ensure data length is the same and calculate z-score
        if len(series_1) > 0 and len(series_1) == len(series_2):
            spread = series_1 - (hedge_ratio * series_2)
            z_score = calculate_zscore(spread).values.tolist()[-1]

            # Check if the trade trigger meets the z-score threshold
            if abs(z_score) >= ZSCORE_THRESH:

                # Ensure that positions are not already open for the pair
                is_base_open = await is_open_positions(client, base_market)
                is_quote_open = await is_open_positions(client, quote_market)

                if not is_base_open and not is_quote_open:

                    # Determine trade sides
                    base_side = "BUY" if z_score < 0 else "SELL"
                    quote_side = "BUY" if z_score > 0 else "SELL"

                    # Calculate acceptable price and size for each market
                    base_price = series_1[-1]
                    quote_price = series_2[-1]
                    accept_base_price = format_number(float(base_price) * (1.01 if z_score < 0 else 0.99), base_market_data["tickSize"])
                    accept_quote_price = format_number(float(quote_price) * (1.01 if z_score > 0 else 0.99), quote_market_data["tickSize"])
                    base_quantity = 1 / base_price * USD_PER_TRADE
                    quote_quantity = 1 / quote_price * USD_PER_TRADE
                    base_size = format_number(base_quantity, base_market_data["stepSize"])
                    quote_size = format_number(quote_quantity, quote_market_data["stepSize"])

                    # Ensure minimum order size
                    base_min_order_size = 1 / float(base_market_data["oraclePrice"])
                    quote_min_order_size = 1 / float(quote_market_data["oraclePrice"])

                    if float(base_quantity) > base_min_order_size and float(quote_quantity) > quote_min_order_size:

                        # Check account balance
                        account = await get_account(client)
                        free_collateral = float(account["freeCollateral"])
                        print(f"Balance: {free_collateral}, Minimum Required: {USD_MIN_COLLATERAL}")

                        # Guard: Ensure sufficient collateral
                        if free_collateral < USD_MIN_COLLATERAL:
                            print("Insufficient collateral. Skipping trade.")
                            continue

                        # Create BotAgent and open trades
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
                            accept_failsafe_base_price=format_number(float(base_price) * (0.05 if z_score < 0 else 1.7), base_market_data["tickSize"]),
                            z_score=z_score,
                            half_life=half_life,
                            hedge_ratio=hedge_ratio
                        )

                        # Attempt to open trades
                        bot_open_dict = await bot_agent.open_trades()

                        # Check for 'createdAtHeight' in the response
                        if "createdAtHeight" in bot_open_dict:
                            created_at_height = bot_open_dict["createdAtHeight"]
                            print(f"Order created at height: {created_at_height}")
                        else:
                            print("Notice: 'createdAtHeight' not found in the order response. Proceeding without it.")
                            if "id" in bot_open_dict:
                                print(f"Order ID: {bot_open_dict['id']}")
                            if "status" in bot_open_dict:
                                print(f"Order Status: {bot_open_dict['status']}")

                        # Handle failure in opening trades
                        if bot_open_dict == "failed":
                            continue

                        # Confirm the trade is live
                        if bot_open_dict.get("pair_status") == "LIVE":
                            bot_agents.append(bot_open_dict)

                            # Save the trade to JSON file
                            with open("bot_agents.json", "w") as f:
                                json.dump(bot_agents, f)

                            print(f"Trade status: Live for {base_market} - {quote_market}")

    # Save agents to the file
    print("Success: All open trades checked")
