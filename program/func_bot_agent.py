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

    async def check_order_status_by_id(self, order_id, retries=3):
        # Allow time to process
        await asyncio.sleep(10)  # Increased delay to ensure the order is registered
        
        # Retry mechanism to check the order status
        for _ in range(retries):
            try:
                # Check if the order ID is valid
                if not order_id or order_id == "order_id":
                    print(f"Invalid order_id: {order_id}")
                    self.order_dict["pair_status"] = "ERROR"
                    return "error"

                # Check order status
                order_status = await check_order_status(self.client, order_id)
                if not order_status:
                    raise ValueError(f"Failed to retrieve order status for order_id: {order_id}")

                if order_status == "FILLED":
                    print(f"Order {order_id} successfully filled.")
                    return "live"

                if order_status == "CANCELED":
                    print(f"Order {order_id} canceled.")
                    self.order_dict["pair_status"] = "FAILED"
                    return "failed"

                # Retry after a short delay
                await asyncio.sleep(10)
            except Exception as e:
                print(f"Error checking order status: {e}")
                self.order_dict["pair_status"] = "ERROR"
        
        # After retries, if order status is not found
        await cancel_order(self.client, order_id)
        print(f"Order {order_id} not filled after retries. Cancelling order.")
        self.order_dict["pair_status"] = "ERROR"
        return "error"

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
            # Ensure the order result contains an order ID
            order_id_m1 = base_order_result.get('order_id')
            if not order_id_m1:
                raise ValueError(f"Error placing base order for {self.market_1}: Order ID not returned.")
            
            self.order_dict["order_id_m1"] = order_id_m1
            self.order_dict["order_time_m1"] = datetime.now().isoformat()
            print(f"First order placed for {self.market_1}: {order_id_m1}")

            # Verify if the order is live
            order_status_m1 = await self.check_order_status_by_id(self.order_dict["order_id_m1"])
            if order_status_m1 != "live":
                raise ValueError(f"Order for {self.market_1} did not go live. Current status: {order_status_m1}")

        except Exception as e:
            print(f"Error placing first order: {e}")
            self.order_dict["pair_status"] = "ERROR"
            self.order_dict["comments"] = f"Error placing order for {self.market_1}: {e}"
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
            # Ensure the order result contains an order ID
            order_id_m2 = quote_order_result.get('order_id')
            if not order_id_m2:
                raise ValueError(f"Error placing quote order for {self.market_2}: Order ID not returned.")

            self.order_dict["order_id_m2"] = order_id_m2
            self.order_dict["order_time_m2"] = datetime.now().isoformat()
            print(f"Second order placed for {self.market_2}: {order_id_m2}")

            # Verify if the order is live
            order_status_m2 = await self.check_order_status_by_id(self.order_dict["order_id_m2"])
            if order_status_m2 != "live":
                raise ValueError(f"Order for {self.market_2} did not go live. Current status: {order_status_m2}")

        except Exception as e:
            print(f"Error placing second order: {e}")
            self.order_dict["pair_status"] = "ERROR"
            self.order_dict["comments"] = f"Error placing order for {self.market_2}: {e}"
            return self.order_dict

        # If both orders are successful
        self.order_dict["pair_status"] = "LIVE"
        print("Both orders placed successfully and are live.")
        return self.order_dict
