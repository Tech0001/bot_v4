from dydx_v4_client import NodeClient, Wallet
from dydx_v4_client.indexer.rest.indexer_client import IndexerClient
from dydx_v4_client.network import TESTNET
from constants import INDEXER_ACCOUNT_ENDPOINT, INDEXER_ENDPOINT_MAINNET, MNEMONIC, DYDX_ADDRESS, MARKET_DATA_MODE, API_TIMEOUT, GRPC_RETRY_ATTEMPTS, GRPC_RETRY_DELAY
from func_public import get_candles_recent
import time
import gc  # Import garbage collection for memory management

class Client:
    def __init__(self, indexer, indexer_account, node, wallet):
        self.indexer = indexer
        self.indexer_account = indexer_account
        self.node = node
        self.wallet = wallet

# Adding retry logic for better stability in node connection
async def connect_dydx():
    market_data_endpoint = INDEXER_ENDPOINT_MAINNET if MARKET_DATA_MODE != "TESTNET" else INDEXER_ACCOUNT_ENDPOINT
    indexer = IndexerClient(host=market_data_endpoint, api_timeout=API_TIMEOUT)
    indexer_account = IndexerClient(host=INDEXER_ACCOUNT_ENDPOINT, api_timeout=API_TIMEOUT)

    node = None
    wallet = None

    for attempt in range(GRPC_RETRY_ATTEMPTS):
        try:
            print(f"Attempt {attempt + 1}/{GRPC_RETRY_ATTEMPTS}: Connecting to node...")
            # Updated: Removed the 'timeout' argument
            node = await NodeClient.connect(TESTNET.node)
            wallet = await Wallet.from_mnemonic(node, MNEMONIC, DYDX_ADDRESS)
            print("Node connection successful.")
            break
        except Exception as e:
            print(f"Error connecting to node: {e}")
            if attempt < GRPC_RETRY_ATTEMPTS - 1:
                print(f"Retrying in {GRPC_RETRY_DELAY} seconds...")
                time.sleep(GRPC_RETRY_DELAY)
            else:
                print("Max retries reached. Exiting.")
                raise e

    client = Client(indexer, indexer_account, node, wallet)
    await check_juristiction(client, "BTC-USD")
    return client

async def check_juristiction(client, market):
    print("Checking Jurisdiction...")
    try:
        # Verifying market connection by fetching recent candles
        await get_candles_recent(client, market)
        print(" ")
        print("--------------------------------------------------------------------------------")
        print("SUCCESS: CONNECTION WORKING")
        print("--------------------------------------------------------------------------------")
        print(" ")
    except Exception as e:
        print(e)
        if "403" in str(e):
            print(" ")
            print("--------------------------------------------------------------------------------")
            print("FAILED: LOCATION ACCESS LIKELY PROHIBITED")
            print("--------------------------------------------------------------------------------")
            print("DYDX likely prohibits use from your country.")
        exit(1)

# New method: to handle memory optimization when processing market data
async def process_market_data_in_batches(client, tradeable_markets, batch_size=10):
    import pandas as pd
    
    close_prices = []
    df = pd.DataFrame()

    # Split markets into smaller batches
    for i in range(0, len(tradeable_markets), batch_size):
        batch = tradeable_markets[i:i+batch_size]
        print(f"Processing batch {i//batch_size + 1}: {batch}")
        
        for market in batch:
            try:
                close_prices_add = await get_candles_recent(client, market)
                df_add = pd.DataFrame(close_prices_add)
                df_add.set_index("datetime", inplace=True)
                df = pd.merge(df, df_add, how="outer", on="datetime", copy=False)
            except Exception as e:
                print(f"Failed to add {market} - {e}")

        # Perform garbage collection to free memory
        del df_add, close_prices_add
        gc.collect()

    # Clean up remaining NaN columns
    nans = df.columns[df.isna().any()].tolist()
    if nans:
        print(f"Dropping columns: {nans}")
        df.drop(columns=nans, inplace=True)

    return df
