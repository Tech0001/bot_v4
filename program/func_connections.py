from dydx_v4_client import NodeClient, Wallet
from dydx_v4_client.indexer.rest.indexer_client import IndexerClient
from dydx_v4_client.network import TESTNET
from constants import INDEXER_ACCOUNT_ENDPOINT, INDEXER_ENDPOINT_MAINNET, MNEMONIC, DYDX_ADDRESS, MARKET_DATA_MODE
from func_public import get_candles_recent

class Client:
    def __init__(self, indexer, indexer_account, node, wallet):
        self.indexer = indexer
        self.indexer_account = indexer_account
        self.node = node
        self.wallet = wallet

async def connect_dydx():
    market_data_endpoint = INDEXER_ENDPOINT_MAINNET if MARKET_DATA_MODE != "TESTNET" else INDEXER_ACCOUNT_ENDPOINT
    indexer = IndexerClient(host=market_data_endpoint, api_timeout=5)
    indexer_account = IndexerClient(host=INDEXER_ACCOUNT_ENDPOINT, api_timeout=5)
    
    # Establishing a connection to the node
    node = await NodeClient.connect(TESTNET.node)
    
    # Creating the wallet from the mnemonic and node connection
    wallet = await Wallet.from_mnemonic(node, MNEMONIC, DYDX_ADDRESS)
    
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
