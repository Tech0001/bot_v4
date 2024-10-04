from dydx_v4_client import NodeClient, Wallet
from dydx_v4_client.indexer.rest.indexer_client import IndexerClient
from dydx_v4_client.network import TESTNET
from constants import INDEXER_ACCOUNT_ENDPOINT, INDEXER_ENDPOINT_MAINNET, MNEMONIC, DYDX_ADDRESS, MARKET_DATA_MODE
from func_public import get_candles_recent

# Client Class
class Client:
    def __init__(self, indexer, indexer_account, node, wallet):
        self.indexer = indexer
        self.indexer_account = indexer_account
        self.node = node
        self.wallet = wallet

# Connect to DYDX
async def connect_dydx():
    market_data_endpoint = INDEXER_ENDPOINT_MAINNET if MARKET_DATA_MODE != "TESTNET" else INDEXER_ACCOUNT_ENDPOINT
    indexer = IndexerClient(host=market_data_endpoint, api_timeout=5)
    indexer_account = IndexerClient(host=INDEXER_ACCOUNT_ENDPOINT, api_timeout=5)
    node = await NodeClient.connect(TESTNET.node)
    wallet = await Wallet.from_mnemonic(node, MNEMONIC, DYDX_ADDRESS)
    client = Client(indexer, indexer_account, node, wallet)
    await check_jurisdiction(client, "BTC-USD")
    return client

# Check Jurisdiction
async def check_jurisdiction(client, market):
    print("Checking Jurisdiction...")
    try:
        await get_candles_recent(client, market)
        print("SUCCESS: CONNECTION WORKING")
    except Exception as e:
        if "403" in str(e):
            print("FAILED: LOCATION ACCESS LIKELY PROHIBITED")
            print("DYDX likely prohibits use from your country.")
        exit(1)
