from func_private import place_market_order, check_order_status, cancel_order
from datetime import datetime
from func_messaging import send_message
import asyncio
import time

class BotAgent:
    """
    Agent to manage the opening of trades and checking the status of orders.
    """

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

        # Initialize order status
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

    async def check_order_status_by_id(self, order_id):
        # Allow time to process
        await asyncio.sleep(2)  # Asynchronous wait

        # Ensure the order_id is valid
        if not order_id or order_id == "order_id":
            print(f"Invalid order_id: {order_id}")
            self.order_dict["pair_status"] = "ERROR"
            return "error"

        # Check order status
        try:
            order_status = await check_order_status(self.client, order_id)
            if not order_status:
                raise ValueError(f"Failed to retrieve order status for order_id: {order_id}")
        except Exception as e:
            print(f"Error checking order status: {e}")
            self.order_dict["pair_status"] = "ERROR"
            return "error"

        if order_status == "CANCELED":
            print(f"Order {order_id} canceled.")
            self.order_dict["pair_status"] = "FAILED"
            return "failed"

        # Wait for 15 seconds to ensure order fills
        await asyncio.sleep(25)
        order_status = await check_order_status(self.client, order_id)

        if order_status == "CANCELED":
            print(f"Order {order_id} canceled after retry.")
            self.order_dict["pair_status"] = "FAILED"
            return "failed"

        if order_status != "FILLED":
            await cancel_order(self.client, order_id)
            self.order_dict["pair_status"] = "ERROR"
            print(f"Order {order_id} not filled. Cancelling order.")
            return "error"

        return "live"

    async def open_trades(self):
        # Place first order
        print(f"Placing first order for {self.market_1}")
        try:
            base_order_result = await place_market_order(
                self.client,
                market=self.market_1,
                side=self.base_side,
                size=self.base_size,
                price=self.base_price,
                reduce_only=False
            )
            if not base_order_result or base_order_result.get('status') == 'failed':
                raise ValueError(f"Error placing base order: {base_order_result.get('error', 'Unknown error')}")

            order_id_m1 = base_order_result.get('order_id')
            if not order_id_m1:
                raise ValueError(f"Failed to retrieve order ID for {self.market_1}")

            self.order_dict["order_id_m1"] = order_id_m1
            self.order_dict["order_time_m1"] = datetime.now().isoformat()
            print(f"First order placed successfully for {self.market_1}: {order_id_m1}")
        except Exception as e:
            print(f"Error placing first order: {e}")
            self.order_dict["pair_status"] = "ERROR"
            self.order_dict["comments"] = f"Error placing order for {self.market_1}: {e}"
            return self.order_dict

        # Check status of the first order
        print(f"Checking status for order {self.order_dict['order_id_m1']}")
        order_status_m1 = await self.check_order_status_by_id(self.order_dict["order_id_m1"])

        if order_status_m1 != "live":
            self.order_dict["pair_status"] = "ERROR"
            self.order_dict["comments"] = f"Order for {self.market_1} failed to fill."
            return self.order_dict

        # Place second order
        print(f"Placing second order for {self.market_2}")
        try:
            quote_order_result = await place_market_order(
                self.client,
                market=self.market_2,
                side=self.quote_side,
                size=self.quote_size,
                price=self.quote_price,
                reduce_only=False
            )
            if not quote_order_result or quote_order_result.get('status') == 'failed':
                raise ValueError(f"Error placing quote order: {quote_order_result.get('error', 'Unknown error')}")

            order_id_m2 = quote_order_result.get('order_id')
            if not order_id_m2:
                raise ValueError(f"Failed to retrieve order ID for {self.market_2}")

            self.order_dict["order_id_m2"] = order_id_m2
            self.order_dict["order_time_m2"] = datetime.now().isoformat()
            print(f"Second order placed successfully for {self.market_2}: {order_id_m2}")
        except Exception as e:
            print(f"Error placing second order: {e}")
            self.order_dict["pair_status"] = "ERROR"
            self.order_dict["comments"] = f"Error placing order for {self.market_2}: {e}"
            return self.order_dict

        # Check status of the second order
        print(f"Checking status for order {self.order_dict['order_id_m2']}")
        order_status_m2 = await self.check_order_status_by_id(self.order_dict["order_id_m2"])

        if order_status_m2 != "live":
            self.order_dict["pair_status"] = "ERROR"
            self.order_dict["comments"] = f"Order for {self.market_2} failed to fill."

            # Attempt to close first order
            try:
                close_order_result = await place_market_order(
                    self.client,
                    market=self.market_1,
                    side=self.quote_side,  # Close with opposite side
                    size=self.base_size,
                    price=self.accept_failsafe_base_price,
                    reduce_only=True
                )
                await asyncio.sleep(2)
                close_order_status = await check_order_status(self.client, close_order_result.get("order_id"))
                if close_order_status != "FILLED":
                    print("Error: Failed to close the first order.")
                    send_message("Critical error: Failed to close first order.")
                    exit(1)
            except Exception as e:
                print(f"Error closing first order: {e}")
                send_message(f"Critical error: {e}")
                exit(1)

        print("Both orders placed successfully.")
        self.order_dict["pair_status"] = "LIVE"
        return self.order_dict
