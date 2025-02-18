import streamlit as st
import pandas as pd
import yfinance as yf
from pycoingecko import CoinGeckoAPI
import datetime
import json
import os
from pathlib import Path
import time
from datetime import datetime, timedelta

# Initialize APIs
cg = CoinGeckoAPI()

# Cache directory setup
CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)

def get_cache_filepath(chain, token_address, year):
    return CACHE_DIR / f"{chain}_{token_address}_{year}.json"

def save_to_cache(data, chain, token_address, year):
    filepath = get_cache_filepath(chain, token_address, year)
    with open(filepath, 'w') as f:
        json.dump(data, f)

def load_from_cache(chain, token_address, year):
    filepath = get_cache_filepath(chain, token_address, year)
    if filepath.exists():
        if time.time() - filepath.stat().st_mtime < 86400:  # 24 hours
            with open(filepath, 'r') as f:
                return json.load(f)
    return None

def get_token_price_data(chain, token_address, year):
    # Check cache first
    cached_data = load_from_cache(chain, token_address, year)
    if cached_data:
        return cached_data

    try:
        platform_ids = {
            "ETH": "ethereum",
            "Arbitrum": "arbitrum-one",
            "Optimism": "optimistic-ethereum",
            "Polygon": "polygon-pos"
        }
        
        platform = platform_ids[chain]
        
        # Get daily prices for the entire year
        daily_prices = {}
        start_date = datetime(year, 1, 1)
        end_date = datetime(year, 12, 31)
        current_date = start_date

        # Batch requests in 90-day chunks to avoid API limitations
        while current_date <= end_date:
            chunk_end = min(current_date + timedelta(days=89), end_date)
            
            try:
                price_data = cg.get_coin_market_chart_range_from_contract_address_by_id(
                    id=platform,
                    contract_address=token_address,
                    vs_currency='usd',
                    from_timestamp=int(current_date.timestamp()),
                    to_timestamp=int(chunk_end.timestamp())
                )

                # Process chunk data
                for timestamp_ms, price in price_data['prices']:
                    date = datetime.fromtimestamp(timestamp_ms/1000).strftime('%Y-%m-%d')
                    daily_prices[date] = price

            except Exception as chunk_error:
                st.warning(f"Could not fetch data for period {current_date.date()} to {chunk_end.date()}: {str(chunk_error)}")
                
            current_date = chunk_end + timedelta(days=1)
            time.sleep(1.5)  # Respect rate limits
            
        if daily_prices:
            save_to_cache(daily_prices, chain, token_address, year)
            return daily_prices
        else:
            st.error("No price data found for this token")
            return None
            
    except Exception as e:
        st.error(f"Error fetching token data: {str(e)}")
        return None

def get_eurusd_rates(year):
    try:
        eurusd = yf.download("EURUSD=X", 
                            start=f"{year}-01-01", 
                            end=f"{year}-12-31",
                            progress=False)
        
        daily_rates = eurusd['Close'].to_dict()
        return {k.strftime('%Y-%m-%d'): v for k, v in daily_rates.items()}
    except Exception as e:
        st.error(f"Error fetching EUR/USD rates: {str(e)}")
        return None

# Streamlit UI
st.title("Crypto Token Price Tracker")

# Input fields
col1, col2, col3 = st.columns(3)

with col1:
    current_year = datetime.now().year
    year = st.selectbox("Select Year", range(2015, current_year + 1))

with col2:
    chain = st.selectbox("Select Chain", ["ETH", "Arbitrum", "Optimism", "Polygon"])

with col3:
    token_address = st.text_input("Token Address")

if st.button("Get Prices"):
    if token_address:
        with st.spinner("Fetching data... This might take a few moments for a full year of data."):
            # Get token prices
            token_prices = get_token_price_data(chain, token_address, year)
            
            # Get EUR/USD rates
            eurusd_rates = get_eurusd_rates(year)
            
            if token_prices and eurusd_rates:
                # Create DataFrame
                data = []
                for date in pd.date_range(start=f"{year}-01-01", end=f"{year}-12-31"):
                    date_str = date.strftime('%Y-%m-%d')
                    token_usd = token_prices.get(date_str)
                    eurusd = eurusd_rates.get(date_str)
                    
                    if token_usd and eurusd:
                        token_eur = token_usd / eurusd
                        data.append({
                            'Date': date_str,
                            'Token/USD': round(token_usd, 6),
                            'EUR/USD': round(eurusd, 4),
                            'Token/EUR': round(token_eur, 6)
                        })
                
                df = pd.DataFrame(data)
                
                # Display table
                st.dataframe(df)
                
                # Download button
                csv = df.to_csv(index=False)
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name=f"token_prices_{chain}_{year}.csv",
                    mime="text/csv"
                )
            else:
                st.error("Could not fetch complete data. Please try again.")
    else:
        st.warning("Please enter a token address")

# Add some usage information
with st.expander("Usage Instructions"):
    st.write("""
    1. Select the year you want to view prices for
    2. Select the blockchain network
    3. Enter the token contract address
    4. Click 'Get Prices' to view the daily prices
    5. Use the Download CSV button to export the data
    
    Example Token Addresses:
    - USDC (Ethereum): 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48
    - USDT (Ethereum): 0xdAC17F958D2ee523a2206206994597C13D831ec7
    - DAI (Ethereum): 0x6B175474E89094C44Da98b954EedeAC495271d0F
    
    Note: Data is cached for 24 hours to avoid API rate limits.
    """)