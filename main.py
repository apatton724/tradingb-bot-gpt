from datetime import datetime, timedelta

import oandapyV20
import oandapyV20.endpoints.orders as orders
# import oandapyV20.endpoints.pricing as pricing
import oandapyV20.endpoints.accounts as accounts
import oandapyV20.endpoints.instruments as instruments

from oandapyV20.exceptions import V20Error
import pandas as pd


# Initialize Oanda API
token =                                                                                                                                             "0810dec3ed286bc7cf6f442ca5d008fb-930b900a89ef665b63614adca926242c"
account_id = "101-001-24102143-002"
client = oandapyV20.API(access_token=token)

def get_rsi(closing_prices, period):
    delta = closing_prices.diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def get_ema(data, period):
    return data.ewm(span=period, adjust=False).mean()

def place_stop_order(instrument, units, order_type, entry_price, stop_price, take_profit):
    # Calculate position size based on 1% risk of account balance
    balance = get_account_balance()
    risk_amount = balance * 0.01
    position_size = int((risk_amount / abs(entry_price - stop_price)) / 1000) * 1000

    entry_price = round(entry_price, 4)  # Format to 5 decimal places
    stop_price = round(stop_price, 4)  # Format to 5 decimal places
    take_profit = round(take_profit, 4)  # Format to 5 decimal places

    order_req = {
        "order": {
            "type": order_type,
            "instrument": instrument,
            "units": str(position_size),
            "price": str(entry_price),
            "stopLossOnFill": {
                "timeInForce": "GTC",
                "price": str(stop_price)
            },
            "takeProfitOnFill": {
                "timeInForce": "GTC",
                "price": str(take_profit)
            }
        }
    }
    print(order_req)
    r = orders.OrderCreate(accountID=account_id, data=order_req)
    print(r)
    try:
        response = client.request(r)
        print("Stop Order placed:", response)
    except V20Error as e:
        print("Error placing order:", e)

def get_account_balance():
    r = accounts.AccountDetails(accountID=account_id)
    response = client.request(r)
    return float(response['account']['balance'])


# Function to check and close pending orders older than 6 hours
def check_and_close_pending_orders():
    try:
        # Create the OrderList request with the account ID
        r = orders.OrderList(accountID=account_id, params={"state": "PENDING"})
        response = client.request(r)

        # Get the current time
        current_time = datetime.utcnow()

        # Check each pending order
        for order in response['orders']:
            # Get the creation time of the order
            # Remove nanoseconds and Z from the timestamp
            timestamp_without_nanos = order['createTime'][:-11]  # Remove the last 10 characters (nanoseconds + 'Z')

            # Parse the timestamp
            creation_time = datetime.strptime(timestamp_without_nanos, "%Y-%m-%dT%H:%M:%S")

            # Calculate the time difference
            time_difference = current_time - creation_time

            # If the order has been open for more than 6 hours, close it
            # if time_difference >= timedelta(hours=6):
            if time_difference >= timedelta(minutes=5):

                try:
                    # Close the pending order using OrderCancel
                    r = orders.OrderCancel(accountID=account_id, orderID=order['id'])
                    response = client.request(r)
                    print(f"Closed pending order: {order['id']}")

                except V20Error as e:
                    print(f"Error closing order {order['id']}: {e}")
        print("No Pending Order open longer than 6 hours found")

    except V20Error as e:
        print(f"Error retrieving pending orders: {e}")


def main():
    instrument = "EUR_USD"
    period = "H1"
    ema_period = 20
    rsi_period = 14
    risk_reward_ratio = 1
    trade_not_found = True

    while trade_not_found:
        check_and_close_pending_orders()

        # Get historical data
        params = {
            "granularity": period,
            "count": 100
        }
        r = instruments.InstrumentsCandles(instrument=instrument, params=params)
        data = client.request(r)
        candles = data['candles']
        df = pd.DataFrame(candles)
        df['time'] = pd.to_datetime(df['time'])
        df.set_index('time', inplace=True)

        # Calculate indicators
        # print(df['mid'])
        closing_prices = df['mid'].apply(lambda x: float(x['c']))
        df['rsi'] = get_rsi(closing_prices, rsi_period)

        # df['rsi'] = get_rsi(df['mid'].apply(lambda x: x['c']), rsi_period)
        df['ema'] = get_ema(closing_prices, ema_period)

        # Check for Long and Short signals
        if df['rsi'].iloc[-1] < 30 and closing_prices.iloc[-1] < df['ema'].iloc[-1]:
            entry_price = df['ema'].iloc[-1]
            stop_price = entry_price - 0.0010  # 10 pips
            take_profit = entry_price + 0.0010 * risk_reward_ratio
            place_stop_order(instrument, 1000, "STOP", entry_price, stop_price, take_profit)
            trade_not_found = False

        elif df['rsi'].iloc[-1] > 70 and df['mid']['c'].iloc[-1] > df['ema'].iloc[-1]:
            entry_price = df['ema'].iloc[-1]
            stop_price = entry_price + 0.0010  # 10 pips
            take_profit = entry_price - 0.0010 * risk_reward_ratio
            place_stop_order(instrument, 1000, "STOP", entry_price, stop_price, take_profit)
        else:
            print("Close: " + str(df['mid']['c'].iloc[-1]))
            print("RSI: " + str(df['rsi'].iloc[-1]))
            print("EMA 20 : " + str(df['ema'].iloc[-1]))
            trade_not_found = False


if __name__ == "__main__":
    main()