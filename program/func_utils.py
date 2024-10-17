from datetime import datetime, timedelta

# Format number to match desired decimal places
def format_number(curr_num: float, match_num: float) -> str:
    """
    Formats curr_num to match the decimal places of match_num.
    Returns the correctly formatted string.
    """
    curr_num_string = f"{curr_num}"
    match_num_string = f"{match_num}"

    if "." in match_num_string:
        match_decimals = len(match_num_string.split(".")[1])
        curr_num_string = f"{curr_num:.{match_decimals}f}"
        return curr_num_string
    else:
        return f"{int(curr_num)}"

# Format the timestamp to ISO format without microseconds
def format_time(timestamp: datetime) -> str:
    """
    Formats the given timestamp into ISO format without microseconds.
    """
    return timestamp.replace(microsecond=0).isoformat()

# Get ISO times for the past intervals
def get_ISO_times() -> dict:
    """
    Generates timestamps for several date ranges to fetch historical data.
    """
    # Define the starting point
    now = datetime.now()

    # Calculate the time intervals (100 hours apart)
    date_start_1 = now - timedelta(hours=100)
    date_start_2 = date_start_1 - timedelta(hours=100)
    date_start_3 = date_start_2 - timedelta(hours=100)
    date_start_4 = date_start_3 - timedelta(hours=100)

    # Create a dictionary of time ranges
    times_dict = {
        "range_1": {
            "from_iso": format_time(date_start_1),
            "to_iso": format_time(now),
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

    return times_dict
