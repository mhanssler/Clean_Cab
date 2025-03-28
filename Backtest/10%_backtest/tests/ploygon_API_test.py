from polygon import RESTClient
import os
def main():
    API_KEY = "Pi5JslRnTPMMpZatCejpinwLP66TFS5M"
    client = RESTClient(api_key = API_KEY)
    print(dir(client), sep = "," "\n")

    print("\n=== Pulling Some Daily Bars for AAPL ===")
    bars = client.list_aggs(
            ticker="AAPL",
            multiplier=1,
            timespan="day",
            from_="2024-12-30",
            to="2024-12-31",
            limit=50
        )
        
        # Convert generator to list
    bars_list = list(bars)
    print(f"Bars list: {bars_list}")
    for bar in bars_list:
        print(f"Date: {bar.timestamp}, Open: {bar.open}, Close: {bar.close}")

        # 5. Clean exit
        print("\nAll done testing Polygon!")

if __name__ == "__main__":
    main()
