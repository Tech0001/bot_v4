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
    """
    Establishes a connection to the dYdX network using the provided mnemonic and account details.
    """
    market_data_endpoint = INDEXER_ENDPOINT_MAINNET if MARKET_DATA_MODE != "TESTNET" else INDEXER_ACCOUNT_ENDPOINT
    try:
        indexer = IndexerClient(host=market_data_endpoint, api_timeout=5)
        indexer_account = IndexerClient(host=INDEXER_ACCOUNT_ENDPOINT, api_timeout=5)

        # Connecting to the node and wallet
        node = await NodeClient.connect(TESTNET.node)
        wallet = await Wallet.from_mnemonic(node, MNEMONIC, DYDX_ADDRESS)

        # Instantiate the client
        client = Client(indexer, indexer_account, node, wallet)
        print("Client connected successfully.")

        # Check the jurisdiction for accessing dYdX
        await check_jurisdiction(client, "BTC-USD")
        return client

    except Exception as e:
        print(f"Error connecting to dYdX: {e}")
        return None

# Check Jurisdiction
async def check_jurisdiction(client, market):
    """
    Checks if the connection is allowed from the user's jurisdiction by attempting to retrieve recent market data.
    """
    print("Checking jurisdiction and connectivity...")
    try:
        await get_candles_recent(client, market)
        print("SUCCESS: Connection and jurisdiction confirmed.")
    except Exception as e:
        if "403" in str(e):
            print("FAILED: Access likely prohibited from your current location.")
            print("dYdX likely restricts access from your country.")
        else:
            print(f"Error while checking jurisdiction: {e}")
        exit(1)
