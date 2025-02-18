import streamlit as st
import pandas as pd
import yfinance as yf
from pycoingecko import CoinGeckoAPI
import datetime
import json
import os
from pathlib import Path
import time

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
        # Check if cache is older than 24 hours
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
        # Convert chain names to CoinGecko platform IDs
        platform_ids = {
            "ETH": "ethereum",
            "Arbitrum": "arbitrum-one",
            "Optimism": "optimistic-ethereum",
            "Polygon": "polygon-pos"
        }
        
        platform = platform_ids[chain]
        
        # Get token data from CoinGecko
        token_data = cg.get_coin_info_from_contract_address_by_id(platform, token_address)
        coin_id = token_data['id']
        
        # Get daily price data for the entire year
        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"
        
        price_data = cg.get_coin_market_chart_range_by_id(
            id=coin_id,
            vs_currency='usd',
            from_timestamp=int(datetime.datetime.strptime(start_date, '%Y-%m-%d').timestamp()),
            to_timestamp=int(datetime.datetime.strptime(end_date, '%Y-%m-%d').timestamp())
        )
        
        # Process price data
        daily_prices = {}
        for timestamp_ms, price in price_data['prices']:
            date = datetime.datetime.fromtimestamp(timestamp_ms/1000).strftime('%Y-%m-%d')
            daily_prices[date] = price
            
        # Cache the results
        save_to_cache(daily_prices, chain, token_address, year)
        return daily_prices
        
    except Exception as e:
        st.error(f"Error fetching token data: {str(e)}")
        return None

def get_eurusd_rates(year):
    try:
        # Get EUR/USD exchange rates from Yahoo Finance
        eurusd = yf.download("EURUSD=X", 
                            start=f"{year}-01-01", 
                            end=f"{year}-12-31",
                            progress=False)
        
        # Convert to daily dictionary format
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
    current_year = datetime.datetime.now().year
    year = st.selectbox("Select Year", range(2015, current_year + 1))

with col2:
    chain = st.selectbox("Select Chain", ["ETH", "Arbitrum", "Optimism", "Polygon"])

with col3:
    token_address = st.text_input("Token Address")

if st.button("Get Prices"):
    if token_address:
        with st.spinner("Fetching data..."):
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
    
    Note: Data is cached for 24 hours to avoid API rate limits.
    """)