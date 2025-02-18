import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta, date, timezone

# Seitenkonfiguration
st.set_page_config(page_title="Token Historical Prices", layout="wide")

st.title("Token Historical Prices in USD & EUR")
st.markdown(
    """
    Diese Webapp ruft für einen angegebenen Token (über Contract-Adresse) auf einer unterstützten Chain (Ethereum, Arbitrum, Optimism)
    historische Preisdaten (USD) von CoinMarketCap ab, holt dazu den historischen USD/EUR-Kurs von exchangerate.host 
    und berechnet den Tokenpreis in EUR.

    Zusätzlich kannst du hier deine API Keys eingeben – weshalb dein CoinMarketCap API Key (Pro) verwendet wird.
    
    Alle Daten des gewählten Jahres werden als Tabelle angezeigt und können als CSV heruntergeladen werden.
    """
)

# Mapping der unterstützen Chains (Plattformen) – ggf. anpassen, falls die Bezeichnungen in CoinMarketCap anders lauten
chain_mapping = {
    "Ethereum": "ethereum",
    "Arbitrum": "arbitrum",
    "Optimism": "optimism"
}

with st.sidebar:
    st.header("Einstellungen")
    selected_chain = st.selectbox("Chain auswählen", list(chain_mapping.keys()))
    contract_address = st.text_input("Token Contract-Adresse", "").strip()
    year = st.number_input("Jahr (vollständig)", min_value=2000, max_value=2100, value=datetime.now().year, step=1)
    
    st.markdown("### API Keys (optional)")
    # Hier wird der CoinMarketCap API Key erwartet – passe das Label ggf. an
    cmc_api_key = st.text_input("CoinMarketCap API Key", type="password",
                                help="Gib hier deinen CoinMarketCap API Key ein (Pro-Version erforderlich für historische Daten).").strip()
    exchange_rate_api_key = st.text_input("ExchangeRate API Key", type="password",
                                          help="Optional: Falls du einen eigenen API Key hast.").strip()
    
    fetch_button = st.button("Daten abrufen")

@st.cache_data(ttl=3600)
def fetch_token_info_cmc(contract_addr: str, platform: str, cmc_api_key: str):
    """
    Ruft Token-Informationen von CoinMarketCap anhand der Contract-Adresse ab.
    Verwendet dazu den /v1/cryptocurrency/map Endpoint.
    """
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/map"
    params = {"address": contract_addr}
    # Optional: Filterung nach Plattform (z. B. Ethereum, Arbitrum, Optimism)
    if platform:
        params["platform"] = platform
    headers = {"X-CMC_PRO_API_KEY": cmc_api_key}
    response = requests.get(url, params=params, headers=headers)
    if response.status_code != 200:
        raise Exception(
            f"Fehler beim Abruf der Token-Informationen (CMC) ({response.status_code}). Response: {response.text}"
        )
    data = response.json().get("data", [])
    if not data:
        raise Exception("Keine Token-Informationen gefunden. Bitte prüfe die Contract-Adresse und den API Key.")
    # Wähle den ersten Treffer (ggf. weitere Logik implementieren, wenn mehrere Ergebnisse vorliegen)
    return data[0]

@st.cache_data(ttl=3600)
def fetch_market_chart_cmc(coin_id: int, start_dt: datetime, end_dt: datetime, cmc_api_key: str):
    """
    Ruft historische OHLCV-Daten (täglich) von CoinMarketCap für den angegebenen Zeitraum ab.
    Nutzt den /v2/cryptocurrency/ohlcv/historical Endpoint.
    """
    url = "https://pro-api.coinmarketcap.com/v2/cryptocurrency/ohlcv/historical"
    params = {
        "id": coin_id,
        "time_start": start_dt.strftime("%Y-%m-%d"),
        "time_end": end_dt.strftime("%Y-%m-%d"),
        "interval": "daily"
    }
    headers = {"X-CMC_PRO_API_KEY": cmc_api_key}
    response = requests.get(url, params=params, headers=headers)
    if response.status_code != 200:
        raise Exception(
            f"Fehler beim Abruf der Preisdaten (CMC) ({response.status_code}). Response: {response.text}"
        )
    return response.json()

@st.cache_data(ttl=86400)
def fetch_exchange_rate(date_str: str, exchange_api_key: str = None):
    """
    Ruft den historischen USD/EUR Wechselkurs für ein bestimmtes Datum von exchangerate.host ab.
    """
    url = f"https://api.exchangerate.host/{date_str}"
    params = {"base": "USD", "symbols": "EUR"}
    if exchange_api_key:
        params["access_key"] = exchange_api_key
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        return data.get("rates", {}).get("EUR", None)
    else:
        return None

if fetch_button:
    if not contract_address:
        st.error("Bitte gib eine Token Contract-Adresse ein.")
    elif not cmc_api_key:
        st.error("Bitte gib einen CoinMarketCap API Key ein.")
    else:
        try:
            with st.spinner("Token-Informationen werden abgerufen..."):
                token_info = fetch_token_info_cmc(contract_address, chain_mapping[selected_chain], cmc_api_key)
            st.success(f"Token gefunden: {token_info.get('name', 'Unbekannt')} ({token_info.get('symbol', '').upper()})")
            
            token_id = token_info.get("id")
            if token_id is None:
                raise Exception("Kein Token ID in den abgerufenen Daten gefunden.")
            
            # Definiere den Zeitraum des gesamten Jahres (UTC)
            start_dt = datetime(year, 1, 1, tzinfo=timezone.utc)
            end_dt = datetime(year, 12, 31, tzinfo=timezone.utc)
            
            with st.spinner("Historische Preisdaten werden abgerufen..."):
                market_data = fetch_market_chart_cmc(token_id, start_dt, end_dt, cmc_api_key)
            
            # Die OHLCV-Daten werden unter market_data["data"]["quotes"] bereitgestellt
            quotes = market_data.get("data", {}).get("quotes", [])
            if not quotes:
                st.error("Es wurden keine Preisdaten gefunden.")
            else:
                # Erstelle ein Mapping: Datum (YYYY-MM-DD) -> Schlusskurs (close price in USD)
                daily_quotes = {}
                for record in quotes:
                    # Beispiel: "time_close": "2025-01-01T23:59:59.000Z"
                    date_str = record.get("time_close", "")[:10]
                    if date_str:
                        close_price = record.get("quote", {}).get("USD", {}).get("close", None)
                        daily_quotes[date_str] = close_price
                
                # Erstelle für jeden Tag des Jahres einen Eintrag (falls keine Daten vorhanden sind, bleibt der Preis None)
                results = []
                current_date = date(year, 1, 1)
                end_date_obj = date(year, 12, 31)
                while current_date <= end_date_obj:
                    day_str = current_date.strftime("%Y-%m-%d")
                    token_price_usd = daily_quotes.get(day_str, None)
                    usd_to_eur = fetch_exchange_rate(day_str, exchange_rate_api_key)
                    token_price_eur = token_price_usd * usd_to_eur if token_price_usd is not None and usd_to_eur is not None else None
                    
                    results.append({
                        "Date": day_str,
                        "Token Price USD": token_price_usd,
                        "USD/EUR": usd_to_eur,
                        "Token Price EUR": token_price_eur
                    })
                    current_date += timedelta(days=1)
                
                df = pd.DataFrame(results)
                st.subheader(f"Preisdaten für {year}")
                st.dataframe(df, use_container_width=True)
                
                csv_data = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="CSV herunterladen",
                    data=csv_data,
                    file_name=f"{token_info.get('symbol', 'token')}_{year}.csv",
                    mime="text/csv"
                )
                
        except Exception as e:
            st.error(f"Fehler: {e}")