import time
import gc  # Import for garbage collection
from dydx_v4_client import NodeClient, Wallet
from dydx_v4_client.indexer.rest.indexer_client import IndexerClient
from dydx_v4_client.network import TESTNET
from constants import INDEXER_ACCOUNT_ENDPOINT, INDEXER_ENDPOINT_MAINNET, MNEMONIC, DYDX_ADDRESS, MARKET_DATA_MODE, API_TIMEOUT, GRPC_RETRY_ATTEMPTS, GRPC_RETRY_DELAY
from func_public import get_candles_recent

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
            # Establish connection to the node
            node = await NodeClient.connect(TESTNET.node)
            # Create wallet using mnemonic
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

    # Ensure memory is managed properly after each attempt
    gc.collect()  # Trigger garbage collection to free up memory after retries

    client = Client(indexer, indexer_account, node, wallet)
    await check_jurisdiction(client, "BTC-USD")
    return client

# Checking jurisdiction to verify if the connection is blocked in certain regions
async def check_jurisdiction(client, market):
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
