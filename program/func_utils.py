from datetime import datetime, timedelta
import numpy as np

# Format number
def format_number(curr_num, match_num):
    """
    Give current number an example of number with decimals desired.
    Function will return the correctly formatted string.
    """
    curr_num_string = f"{curr_num}"
    match_num_string = f"{match_num}"

    if "." in match_num_string:
        match_decimals = len(match_num_string.split(".")[1])
        curr_num_string = f"{curr_num:.{match_decimals}f}"
        curr_num_string = curr_num_string[:]
        return curr_num_string
    else:
        return f"{int(curr_num)}"

# Format time
def format_time(timestamp):
    return timestamp.replace(microsecond=0).isoformat()

# Get ISO Times
def get_ISO_times():
    """
    Returns dictionary with four date ranges, formatted in ISO format.
    """
    # Get timestamps
    date_start_0 = datetime.now()
    date_start_1 = date_start_0 - timedelta(hours=100)
    date_start_2 = date_start_1 - timedelta(hours=100)
    date_start_3 = date_start_2 - timedelta(hours=100)
    date_start_4 = date_start_3 - timedelta(hours=100)

    # Format datetimes
    times_dict = {
        "range_1": {
            "from_iso": format_time(date_start_1),
            "to_iso": format_time(date_start_0),
        },
        "range_2": {
            "from_iso": format_time(date_start_2),
            "to_iso": format_time(date_start_1),
        },
        "range_3": {
            "from_iso": format_time(date_start_3),
            "to_iso": format_time(date_start_2),
        },
        "range_4": {
            "from_iso": format_time(date_start_4),
            "to_iso": format_time(date_start_3),
        },
    }

    # Return result
    return times_dict

# Calculate z-score
def calculate_zscore(spread):
    """
    Calculates the z-score of the spread between two assets over time.
    """
    mean = np.mean(spread)
    std = np.std(spread)
    zscore = (spread - mean) / std
    return zscore

# Get recent candles
async def get_candles_recent(client, market):
    """
    Retrieves the most recent candles for the specified market from the dYdX API.
    """
    candles = await client.indexer.get_candles(market=market)
    return candles

# Get markets
async def get_markets(client):
    """
    Retrieves the available markets from the dYdX API.
    """
    markets = await client.indexer.get_markets()
    return markets

# Get open positions
async def get_open_positions(client):
    """
    Retrieves the currently open positions for the connected wallet.
    """
    positions = await client.indexer_account.get_subaccount_perpetual_positions(client.wallet.address, 0)
    return positions

# Get account information
async def get_account(client):
    """
    Retrieves the account details, including available collateral and balances.
    """
    account = await client.indexer_account.get_subaccount(client.wallet.address, 0)
    return account
