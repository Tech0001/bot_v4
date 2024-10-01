# Import necessary functions and constants
from func_private import place_market_order, check_order_status, cancel_order, get_order
from datetime import datetime
import asyncio
import logging
import random  # Import for generating unique order IDs
from constants import DYDX_ADDRESS, MNEMONIC  # Use MNEMONIC and DYDX_ADDRESS from your provided terms

# Class: Agent for managing opening and checking trades
class BotAgent:

    # Initialize class
    def __init__(
        self,
        client,
        market_1,
        market_2,
        base_side,
        base_size,
        base_price,
        quote_side,
        quote_size,
        quote_price,
        accept_failsafe_base_price,
        z_score,
        half_life,
        hedge_ratio,
        time_in_force="DEFAULT",  # Added for TIF
    ):
        self.client = client
        self.market_1 = market_1
        self.market_2 = market_2
        self.base_side = base_side
        self.base_size = base_size
        self.base_price = base_price
        self.quote_side = quote_side
        self.quote_size = quote_size
        self.quote_price = quote_price
        self.accept_failsafe_base_price = accept_failsafe_base_price
        self.z_score = z_score
        self.half_life = half_life
        self.hedge_ratio = hedge_ratio
        self.time_in_force = time_in_force  # Keep time in force setting for orders

        # Initialize output variable
        self.order_dict = {
            "market_1": market_1,
            "market_2": market_2,
            "hedge_ratio": hedge_ratio,
            "z_score": z_score,
            "half_life": half_life,
            "order_id_m1": "",
            "order_m1_size": base_size,
            "order_m1_side": base_side,
            "order_time_m1": "",
            "order_id_m2": "",
            "order_m2_size": quote_size,
            "order_m2_side": quote_side,
            "order_time_m2": "",
            "pair_status": "",
            "comments": "",
        }

    # Retry mechanism to fetch the order details if `createdAtHeight` is missing
    async def retry_fetch_order(self, order_id, retries=3, delay=3):
        order = None
        for attempt in range(retries):
            order = await get_order(self.client, order_id)
            if order and "createdAtHeight" in order:
                logging.info(f"Order found with createdAtHeight: {order['createdAtHeight']}")
                return order
            logging.warning(f"Retry {attempt + 1}/{retries} - Waiting for createdAtHeight...")
            await asyncio.sleep(delay)
        logging.error(f"Warning: 'createdAtHeight' not found after {retries} retries. Proceeding without it.")
        return order

    # Check order status by id with retries
    async def check_order_status_by_id(self, order_id, retries=3, delay=3):
        for attempt in range(retries):
            await asyncio.sleep(2)
            order_status = await check_order_status(self.client, order_id)

            if order_status == "CANCELED":
                logging.error(f"{self.market_1} vs {self.market_2} - Order canceled...")
                self.order_dict["pair_status"] = "FAILED"
                return "failed"

            if order_status == "FILLED":
                return "live"

            logging.warning(f"Order status not filled. Attempt {attempt + 1}/{retries}. Retrying...")
            await asyncio.sleep(delay)

        logging.error(f"Order status check failed after {retries} retries. Canceling order...")
        await cancel_order(self.client, order_id)
        self.order_dict["pair_status"] = "ERROR"
        return "error"

    # Open trades with improved retry logic
    async def open_trades(self):
        logging.info(f"{self.market_1}: Placing first order (Side: {self.base_side}, Size: {self.base_size}, Price: {self.base_price})")

        try:
            # Unique order ID generation using random
            order_id_m1 = f"{DYDX_ADDRESS}_{random.randint(1, 100000)}"

            # Place first order
            (base_order, order_id) = await place_market_order(
                self.client,
                market=self.market_1,
                side=self.base_side,
                size=self.base_size,
                price=self.base_price,
                reduce_only=False
            )
            self.order_dict["order_id_m1"] = order_id_m1
            self.order_dict["order_time_m1"] = datetime.now().isoformat()
            logging.info("First order sent...")

            base_order = await self.retry_fetch_order(order_id_m1)

            if base_order:
                self.process_order_response(base_order, "m1")
        except Exception as e:
            logging.error(f"Error placing first order: {e}")
            self.order_dict["pair_status"] = "ERROR"
            self.order_dict["comments"] = f"Market 1 {self.market_1}: {e}"
            return self.order_dict

        logging.info("Checking first order status...")
        order_status_m1 = await self.check_order_status_by_id(self.order_dict["order_id_m1"])
        if order_status_m1 != "live":
            self.order_dict["pair_status"] = "ERROR"
            self.order_dict["comments"] = f"{self.market_1} failed to fill"
            return self.order_dict

        logging.info(f"{self.market_2}: Placing second order (Side: {self.quote_side}, Size: {self.quote_size}, Price: {self.quote_price})")

        try:
            # Unique order ID generation for second market
            order_id_m2 = f"{DYDX_ADDRESS}_{random.randint(1, 100000)}"

            # Place second order
            (quote_order, order_id) = await place_market_order(
                self.client,
                market=self.market_2,
                side=self.quote_side,
                size=self.quote_size,
                price=self.quote_price,
                reduce_only=False
            )
            self.order_dict["order_id_m2"] = order_id_m2
            self.order_dict["order_time_m2"] = datetime.now().isoformat()
            logging.info("Second order sent...")

            quote_order = await self.retry_fetch_order(order_id_m2)

            if quote_order:
                self.process_order_response(quote_order, "m2")
        except Exception as e:
            logging.error(f"Error placing second order: {e}")
            self.order_dict["pair_status"] = "ERROR"
            self.order_dict["comments"] = f"Market 2 {self.market_2}: {e}"
            return self.order_dict

        logging.info("Checking second order status...")
        order_status_m2 = await self.check_order_status_by_id(self.order_dict["order_id_m2"])

        if order_status_m2 != "live":
            self.order_dict["pair_status"] = "ERROR"
            self.order_dict["comments"] = f"{self.market_2} failed to fill"

            try:
                logging.info(f"Attempting to close position on {self.market_1} due to failed second order...")
                (close_order, order_id) = await place_market_order(
                    self.client,
                    market=self.market_1,
                    side=self.quote_side,
                    size=self.base_size,
                    price=self.accept_failsafe_base_price,
                    reduce_only=True
                )

                await asyncio.sleep(2)
                order_status_close_order = await check_order_status(self.client, order_id)
                if order_status_close_order != "FILLED":
                    logging.error(f"Error closing position on {self.market_1}. Status: {order_status_close_order}")
                    logging.error(f"ABORT PROGRAM - Unable to close position on {self.market_1}")
                    self.order_dict["comments"] = f"ABORT PROGRAM: Failed to close position on {self.market_1}"
                    exit(1)
                else:
                    logging.info(f"Position closed successfully for {self.market_1}")

            except Exception as e:
                logging.error(f"Error closing first order on {self.market_1}: {e}")
                self.order_dict["pair_status"] = "ERROR"
                self.order_dict["comments"] = f"Close Market 1 {self.market_1}: {e}"
                logging.error(f"ABORT PROGRAM - Exception while closing first order")
                exit(1)

        logging.info("SUCCESS: LIVE PAIR")
        self.order_dict["pair_status"] = "LIVE"
        return self.order_dict

    # Process the order response to log details
    def process_order_response(self, order, order_name):
        if "createdAtHeight" in order:
            logging.info(f"{order_name}: Order created at block height: {order['createdAtHeight']}")
        else:
            logging.warning(f"Notice: 'createdAtHeight' not found for {order_name}. Proceeding without it.")
