# Import necessary functions and constants
from func_private import place_market_order, check_order_status, cancel_order
from datetime import datetime
import time

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

    # Check order status by id
    async def check_order_status_by_id(self, order_id):
        time.sleep(2)
        order_status = await check_order_status(self.client, order_id)

        if order_status == "CANCELED":
            print(f"{self.market_1} vs {self.market_2} - Order canceled...")
            self.order_dict["pair_status"] = "FAILED"
            return "failed"

        if order_status != "FAILED":
            time.sleep(15)
            order_status = await check_order_status(self.client, order_id)

            if order_status == "CANCELED":
                print(f"{self.market_1} vs {self.market_2} - Order canceled...")
                self.order_dict["pair_status"] = "FAILED"
                return "failed"

            if order_status != "FILLED":
                await cancel_order(self.client, order_id)
                self.order_dict["pair_status"] = "ERROR"
                print(f"{self.market_1} vs {self.market_2} - Order error. Cancellation request sent.")
                return "error"

        return "live"

    # Open trades
    async def open_trades(self):
        print(f"{self.market_1}: Placing first order...")
        print(f"Side: {self.base_side}, Size: {self.base_size}, Price: {self.base_price}")

        try:
            (base_order, order_id) = await place_market_order(
                self.client,
                market=self.market_1,
                side=self.base_side,
                size=self.base_size,
                price=self.base_price,
                reduce_only=False
            )
            self.order_dict["order_id_m1"] = order_id
            self.order_dict["order_time_m1"] = datetime.now().isoformat()
            print("First order sent...")
        except Exception as e:
            print(f"Error placing first order: {e}")
            self.order_dict["pair_status"] = "ERROR"
            self.order_dict["comments"] = f"Market 1 {self.market_1}: {e}"
            return self.order_dict

        print("Checking first order status...")
        order_status_m1 = await self.check_order_status_by_id(self.order_dict["order_id_m1"])
        if order_status_m1 != "live":
            self.order_dict["pair_status"] = "ERROR"
            self.order_dict["comments"] = f"{self.market_1} failed to fill"
            return self.order_dict

        print(f"{self.market_2}: Placing second order...")
        print(f"Side: {self.quote_side}, Size: {self.quote_size}, Price: {self.quote_price}")

        try:
            (quote_order, order_id) = await place_market_order(
                self.client,
                market=self.market_2,
                side=self.quote_side,
                size=self.quote_size,
                price=self.quote_price,
                reduce_only=False
            )
            self.order_dict["order_id_m2"] = order_id
            self.order_dict["order_time_m2"] = datetime.now().isoformat()
            print("Second order sent...")
        except Exception as e:
            print(f"Error placing second order: {e}")
            self.order_dict["pair_status"] = "ERROR"
            self.order_dict["comments"] = f"Market 2 {self.market_2}: {e}"
            return self.order_dict

        print("Checking second order status...")
        order_status_m2 = await self.check_order_status_by_id(self.order_dict["order_id_m2"])

        if order_status_m2 != "live":
            self.order_dict["pair_status"] = "ERROR"
            self.order_dict["comments"] = f"{self.market_2} failed to fill"

            try:
                (close_order, order_id) = await place_market_order(
                    self.client,
                    market=self.market_1,
                    side=self.quote_side,
                    size=self.base_size,
                    price=self.accept_failsafe_base_price,
                    reduce_only=True
                )

                time.sleep(2)
                order_status_close_order = await check_order_status(self.client, order_id)
                if order_status_close_order != "FILLED":
                    print("ABORT PROGRAM")
                    exit(1)
            except Exception as e:
                print(f"Error closing first order: {e}")
                self.order_dict["pair_status"] = "ERROR"
                self.order_dict["comments"] = f"Close Market 1 {self.market_1}: {e}"
                exit(1)

        print("SUCCESS: LIVE PAIR")
        self.order_dict["pair_status"] = "LIVE"
        return self.order_dict
