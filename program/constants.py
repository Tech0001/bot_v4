# from dydx3.constants import API_HOST_MAINNET, API_HOST_GOERLI
from decouple import config

# For gathering tesnet data or live market data for cointegration calculation
MARKET_DATA_MODE = "TESTNET" # vs "MAINNET"

# Close all open positions and orders
ABORT_ALL_POSITIONS = False

# Find Cointegrated Pairs
FIND_COINTEGRATED = False

# Manage Exits
MANAGE_EXITS = True

# Place Trades
PLACE_TRADES = True

# Resolution
RESOLUTION = "1HOUR"

# Stats Window
WINDOW = 21

# Thresholds - Opening
MAX_HALF_LIFE = 24
ZSCORE_THRESH = 1.1
USD_PER_TRADE = 25
USD_MIN_COLLATERAL = 100

# Thresholds - Closing
CLOSE_AT_ZSCORE_CROSS = True

# constants.py

# Endpoint for Account Queries on Testnet
INDEXER_ENDPOINT_TESTNET = "https://indexer.v4testnet.dydx.exchange"
INDEXER_ENDPOINT_MAINNET = "https://indexer.dydx.exchange"
INDEXER_ACCOUNT_ENDPOINT = INDEXER_ENDPOINT_TESTNET  # or INDEXER_ENDPOINT_MAINNET for live environment

# gRPC Endpoints
GRPC_ENDPOINT_TESTNET = "grpc.testnet.dydx.exchange:443"
GRPC_ENDPOINT_MAINNET = "grpc.mainnet.dydx.exchange:443"
INDEXER_GRPC_ENDPOINT_TESTNET = "indexer.testnet.dydx.exchange:443"
INDEXER_GRPC_ENDPOINT_MAINNET = "indexer.mainnet.dydx.exchange:443"



# Endpoint for Account Queries on Testnet
INDEXER_ENDPOINT_TESTNET = "https://indexer.v4testnet.dydx.exchange"
INDEXER_ENDPOINT_MAINNET = "https://indexer.dydx.exchange"
INDEXER_ACCOUNT_ENDPOINT = INDEXER_ENDPOINT_TESTNET  # or INDEXER_ENDPOINT_MAINNET for live environment


# Environment Variables
DYDX_ADDRESS = config("DYDX_ADDRESS")
SECRET_PHRASE = config("SECRET_PHRASE")
MNEMONIC = (SECRET_PHRASE)
TELEGRAM_TOKEN = config("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = config("TELEGRAM_CHAT_ID")