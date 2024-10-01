import time
import logging
import asyncio
import gc  # For garbage collection to manage memory
from dydx_v4_client import NodeClient, Wallet
from dydx_v4_client.indexer.rest.indexer_client import IndexerClient
from dydx_v4_client.indexer.socket.websocket import IndexerSocket
from dydx_v4_client.network import TESTNET
from constants import INDEXER_ACCOUNT_ENDPOINT, INDEXER_ENDPOINT_MAINNET, MNEMONIC, DYDX_ADDRESS, MARKET_DATA_MODE, API_TIMEOUT, GRPC_RETRY_ATTEMPTS, GRPC_RETRY_DELAY
from func_public import get_candles_recent
from grpc import StatusCode  # To catch specific gRPC errors

# Logging setup for better tracking
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

class Client:
    def __init__(self, indexer, indexer_account, node, wallet, websocket):
        self.indexer = indexer
        self.indexer_account = indexer_account
        self.node = node
        self.wallet = wallet
        self.websocket = websocket

# Adding retry logic with exponential backoff
async def connect_dydx():
    market_data_endpoint = INDEXER_ENDPOINT_MAINNET if MARKET_DATA_MODE != "TESTNET" else INDEXER_ACCOUNT_ENDPOINT
    indexer = IndexerClient(host=market_data_endpoint, api_timeout=API_TIMEOUT)
    indexer_account = IndexerClient(host=INDEXER_ACCOUNT_ENDPOINT, api_timeout=API_TIMEOUT)

    node = None
    wallet = None
    websocket = None
    backoff = GRPC_RETRY_DELAY

    for attempt in range(GRPC_RETRY_ATTEMPTS):
        try:
            logging.info(f"Attempt {attempt + 1}/{GRPC_RETRY_ATTEMPTS}: Connecting to node...")
            node = await NodeClient.connect(TESTNET.node)
            wallet = await Wallet.from_mnemonic(node, MNEMONIC, DYDX_ADDRESS)
            
            # WebSocket Connection
            websocket = IndexerSocket(TESTNET.websocket_indexer, on_open=on_open, on_message=on_message)
            await websocket.connect()  # Connect to the WebSocket for real-time data

            logging.info("Node and WebSocket connection successful.")
            break
        except Exception as e:
            logging.error(f"Error connecting to node or WebSocket: {e}")

            # Specific handling for gRPC 503 errors (Server Unavailable)
            if isinstance(e, StatusCode) and e.code() == StatusCode.UNAVAILABLE:
                logging.error("gRPC UNAVAILABLE (503): The server is unavailable. Retrying...")
            
            if attempt < GRPC_RETRY_ATTEMPTS - 1:
                logging.info(f"Retrying in {backoff} seconds...")
                time.sleep(backoff)
                backoff *= 2  # Exponential backoff
            else:
                logging.error("Max retries reached. Exiting.")
                raise e

    # Call garbage collection to free memory and prevent crashes
    gc.collect()

    client = Client(indexer, indexer_account, node, wallet, websocket)
    await check_jurisdiction(client, "BTC-USD")
    return client

# Checking jurisdiction to verify if the connection is blocked in certain regions
async def check_jurisdiction(client, market):
    logging.info("Checking Jurisdiction...")
    try:
        await get_candles_recent(client, market)
        logging.info(" ")
        logging.info("--------------------------------------------------------------------------------")
        logging.info("SUCCESS: CONNECTION WORKING")
        logging.info("--------------------------------------------------------------------------------")
        logging.info(" ")
    except Exception as e:
        logging.error(e)
        if "403" in str(e):
            logging.error(" ")
            logging.error("--------------------------------------------------------------------------------")
            logging.error("FAILED: LOCATION ACCESS LIKELY PROHIBITED")
            logging.error("--------------------------------------------------------------------------------")
            logging.error("DYDX likely prohibits use from your country.")
        exit(1)

# WebSocket event handling (from the example)
def on_open(ws):
    ws.subaccounts.subscribe(address=DYDX_ADDRESS, subaccount_number=0)
    ws.markets.subscribe()
    ws.trades.subscribe(id="ETH-USD")
    ws.order_book.subscribe(id="ETH-USD")
    logging.info("WebSocket subscribed to subaccounts, markets, trades, order_book.")

def on_message(ws, message):
    logging.info(f"WebSocket message received: {message}")

