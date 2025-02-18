import streamlit as st
import pandas as pd
import requests
from datetime import datetime

# Konfiguration
COINGECKO_API_URL = "https://api.coingecko.com/api/v3"
ECB_API_URL = "https://api.statistiken.bundesbank.de/rest/data/EXR/B.USD.EUR.SP00.A"

# Chain-ID Mapping für CoinGecko
CHAIN_MAPPING = {
    "ethereum": "eth",
    "polygon": "matic",
    "bnb smart chain": "binance-smart-chain",
    "avalanche": "avalanche"
}

@st.cache_data(ttl=3600)
def get_token_price(token_address: str, chain: str, year: int) -> pd.DataFrame:
    """Holt historische Token-Preise von CoinGecko"""
    try:
        chain_id = CHAIN_MAPPING.get(chain.lower())
        if not chain_id:
            raise ValueError(f"Unsupported chain: {chain}")
        
        end_date = datetime(year, 12, 31)
        days = (end_date - datetime(year, 1, 1)).days
        
        response = requests.get(
            f"{COINGECKO_API_URL}/coins/{chain_id}/contract/{token_address}/market_chart/",
            params={"vs_currency": "usd", "days": days, "interval": "daily"}
        )
        response.raise_for_status()
        
        data = response.json()
        df = pd.DataFrame(data["prices"], columns=["timestamp", "usd"])
        df["date"] = pd.to_datetime(df["timestamp"], unit="ms").dt.date
        return df[["date", "usd"]]
    
    except requests.exceptions.HTTPError as e:
        if "404" in str(e):
            raise ValueError(f"Token mit Adresse {token_address} nicht auf {chain} gefunden")
        raise

@st.cache_data(ttl=86400)
def get_eur_usd_rate(year: int) -> pd.DataFrame:
    """Holt EUR/USD Kurse mit Forward-Filling für Wochenenden"""
    try:
        # ECB Daten holen
        response = requests.get(
            ECB_API_URL,
            params={"format": "csv", "startPeriod": f"{year}-01-01"}
        )
        response.raise_for_status()
        
        # Daten verarbeiten
        df = pd.read_csv(response.text.split("\n", 5)[5], sep=";")
        df = df.rename(columns={"Wert": "eur_usd", "Zeit": "date"})
        df["date"] = pd.to_datetime(df["date"]).dt.date
        
        # Vollständiges Datumsraster erstellen
        full_dates = pd.date_range(start=f"{year}-01-01", end=f"{year}-12-31", freq="D").date
        df_full = pd.DataFrame({"date": full_dates})
        
        # Merge und Forward-Fill
        df_full = df_full.merge(df, on="date", how="left")
        df_full["eur_usd"] = df_full["eur_usd"].ffill()
        
        return df_full[["date", "eur_usd"]]
    
    except Exception as e:
        raise RuntimeError(f"Fehler beim Laden der EUR/USD Daten: {str(e)}")

def main():
    st.set_page_config(page_title="Crypto Price Exporter", layout="wide")
    st.title("🚀 Crypto Price Historie Export")
    
    with st.form("input_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            token_address = st.text_input("Token Contract Address", value="0xdac17f958d2ee523a2206206994597c13d831ec7")
        with col2:
            chain = st.selectbox("Blockchain", ["Ethereum", "Polygon", "BNB Smart Chain", "Avalanche"])
        with col3:
            year = st.number_input("Jahr", min_value=2015, max_value=datetime.now().year, value=2023)
        
        submitted = st.form_submit_button("Daten abrufen")
    
    if submitted:
        with st.spinner("Daten werden geladen..."):
            try:
                # Daten abrufen
                price_df = get_token_price(token_address.strip(), chain.lower(), year)
                eur_usd_df = get_eur_usd_rate(year)
                
                # Zusammenführen und berechnen
                merged_df = pd.merge(price_df, eur_usd_df, on="date", how="left")
                merged_df["eur"] = merged_df["usd"] * merged_df["eur_usd"]
                
                # Formatierung
                merged_df = merged_df.round({"usd": 4, "eur_usd": 4, "eur": 4})
                merged_df.insert(0, "year", merged_df["date"].dt.year)
                merged_df.insert(1, "month", merged_df["date"].dt.month)
                merged_df.insert(2, "day", merged_df["date"].dt.day)
                
                # Anzeige
                st.success(f"🟢 {len(merged_df)} Tage gefunden")
                st.dataframe(merged_df.drop(columns=["date"]), height=500)
                
                # Download
                csv = merged_df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="📥 CSV Export",
                    data=csv,
                    file_name=f"prices_{token_address[:6]}_{chain}_{year}.csv",
                    mime="text/csv"
                )
            
            except ValueError as e:
                st.error(f"🔴 Fehler: {str(e)}")
            except Exception as e:
                st.error(f"🔴 Unerwarteter Fehler: {str(e)}")

if __name__ == "__main__":
    main()