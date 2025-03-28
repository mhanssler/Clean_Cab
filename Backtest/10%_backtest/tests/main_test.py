import os
import pandas as pd
from datetime import datetime, timedelta
from polygon import RESTClient

########################################
# 1) Set up your Polygon API Key & Client
########################################

API_KEY = ("Pi5JslRnTPMMpZatCejpinwLP66TFS5M")  # or "YOUR_ACTUAL_API_KEY"
if not API_KEY:
    print("Please set your POLYGON_API_KEY environment variable before running.")
    raise SystemExit

client = RESTClient(api_key=API_KEY)

########################################
# 2) Helper Functions
########################################

def get_earnings_calendar_polygon(ticker, start_date, end_date, client):
    """
    Fetch a list of quarterly financial records from Polygon for 'ticker'.
    We'll approximate the 'earnings announcement date' as the 'filingDate'.
    
    Returns a DataFrame of [ticker, filingDate] rows filtered to 'start_date'...'end_date'.
    """
    # Convert to YYYY-MM-DD strings for time filter if needed
    # (Polygon docs do not always require date filters for financials, 
    #  but you can do them if the endpoint supports date range queries.)
    
    response = client.list_financials(
        ticker=ticker,
        timeframe="quarterly",
        limit=500,        # up to 500 records (enough for many years)
        sort="filingDate",
        order="asc"       # older first
    )
    data = list(response)
    print(data)
    if not data:
        return pd.DataFrame(columns=["ticker", "filingDate"])

    df = pd.DataFrame(data)
    
    # We will rename the date column for clarity
    if "filingDate" not in df.columns:
        print(f"No filingDate in financials for {ticker}, skipping.")
        return pd.DataFrame(columns=["ticker", "filingDate"])

    df["filingDate"] = pd.to_datetime(df["filingDate"]).dt.normalize()
    df = df.rename(columns={"filingDate": "EarningsDate"})
    
    # Filter by date range
    # We only keep earnings dates within our backtest window
    mask = (df["EarningsDate"] >= start_date) & (df["EarningsDate"] <= end_date)
    df = df.loc[mask].copy()
    
    # Keep minimal columns
    df = df[["ticker", "EarningsDate"]]
    df.drop_duplicates(inplace=True)
    return df

def get_daily_bars_polygon(ticker, start_date, end_date, client):
    """
    Retrieve daily OHLC data from Polygon for 'ticker' in the given date range.
    Returns a DataFrame with columns: [Date, Open, High, Low, Close, Volume].
    """
    # Polygon uses "YYYY-MM-DD" strings
    from_str = start_date.strftime("%Y-%m-%d")
    to_str = end_date.strftime("%Y-%m-%d")
    
    bars = client.list_aggs(
        ticker=ticker,
        multiplier=1,
        timespan="day",
        from_=from_str,
        to=to_str,
        limit=50000  # large limit to ensure we get all bars
    )
    bars_list = list(bars)
    
    if not bars_list:
        return pd.DataFrame(columns=["Date", "Open", "Close", "High", "Low", "Volume"])
    
    records = []
    for bar in bars_list:
        # bar is an Agg object; we use dot notation
        # Typically we have bar.timestamp, bar.open, bar.high, bar.low, bar.close, bar.volume, ...
        records.append({
            "Date": datetime.utcfromtimestamp(bar.timestamp/1000).date(),
            "Open": bar.open,
            "High": bar.high,
            "Low": bar.low,
            "Close": bar.close,
            "Volume": bar.volume
        })
    
    df = pd.DataFrame(records)
    df.sort_values("Date", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df

def backtest_earnings_spike(tickers, start_date, end_date, client, jump_threshold=0.10, holding_days=180):
    """
    Backtests the strategy:
    1. For each ticker, retrieve daily bars and approximate earnings days.
    2. On an earnings day, check if NEXT day's open >= previous day's close * (1 + jump_threshold).
    3. If yes, buy at next day's open, hold for 'holding_days' days, then sell at next available open.
    4. Calculate each trade's return, compile results in a DataFrame.
    """
    all_trades = []
    
    for ticker in tickers:
        print(f"\nProcessing {ticker}...")

        # 1) Get daily bars
        price_df = get_daily_bars_polygon(ticker, start_date, end_date, client)
        if price_df.empty:
            print(f"No price data for {ticker}, skipping.")
            continue
        
        # 2) Get Earnings dates from Polygon
        earnings_df = get_earnings_calendar_polygon(ticker, start_date, end_date, client)
        if earnings_df.empty:
            print(f"No earnings data for {ticker}, skipping.")
            continue
        
        # Convert to datetime.date
        price_df["Date"] = pd.to_datetime(price_df["Date"])
        earnings_df["EarningsDate"] = pd.to_datetime(earnings_df["EarningsDate"])
        
        # We'll merge a flag for "Earnings Day"
        price_df["EarningsFlag"] = price_df["Date"].isin(earnings_df["EarningsDate"])
        
        # We need quick ways to get next day open vs. previous day close
        # We'll shift 'Open' backward by -1 day so that today's row holds tomorrow's open.
        price_df["NextDayOpen"] = price_df["Open"].shift(-1)
        # The "previous day close" is just the same row's 'Close' if we consider "earnings day" = that row.
        # But we might want to confirm the day-of-earnings is correct. We'll assume we buy on the day after an earnings day.
        
        for i in range(len(price_df) - 1):
            row = price_df.iloc[i]
            
            if row["EarningsFlag"]:
                prev_close = row["Close"]
                next_open = price_df.iloc[i+1]["Open"]  # or row["NextDayOpen"]
                
                if pd.isna(next_open):
                    # No next day open, maybe end of data range
                    continue
                
                # Check the jump
                jump = (next_open - prev_close) / prev_close
                if jump >= jump_threshold:
                    # We generate a trade signal
                    buy_date = price_df.iloc[i+1]["Date"]
                    buy_price = next_open
                    
                    # Sell date ~ 180 days later
                    sell_date_candidate = buy_date + timedelta(days=holding_days)
                    
                    # We find the next available row in price_df with Date >= sell_date_candidate
                    future_rows = price_df[price_df["Date"] >= sell_date_candidate]
                    if future_rows.empty:
                        # No data to sell, skip
                        continue
                    sell_row = future_rows.iloc[0]
                    sell_date = sell_row["Date"]
                    sell_price = sell_row["Open"]  # We sell at open on that day
                    trade_return = (sell_price - buy_price) / buy_price
                    
                    all_trades.append({
                        "Ticker": ticker,
                        "EarningsDate": row["Date"],
                        "BuyDate": buy_date,
                        "BuyPrice": buy_price,
                        "SellDate": sell_date,
                        "SellPrice": sell_price,
                        "JumpPct": jump,
                        "Return6mo": trade_return
                    })
    
    results_df = pd.DataFrame(all_trades)
    return results_df

########################################
# 3) Main Execution / Usage Example
########################################

if __name__ == "__main__":
    # Define your backtest window
    start_dt = datetime(2018, 1, 1)
    end_dt   = datetime(2023, 12, 31)
    
    # Example set of tickers (you could expand this)
    ticker_list = ["AAPL", "MSFT", "TSLA", "GOOGL"]
    
    # Run the backtest
    results = backtest_earnings_spike(
        tickers=ticker_list,
        start_date=start_dt,
        end_date=end_dt,
        client=client,
        jump_threshold=0.10,   # 10% jump
        holding_days=180       # ~6 months
    )
    
    print("\nBacktest Results:")
    print(results)
    
    if not results.empty:
        avg_return = results["Return6mo"].mean()
        print(f"\nAverage 6-month Return for all signals: {avg_return:.2%}")
