import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta, date, timezone, time

# Seitenkonfiguration
st.set_page_config(page_title="Token Historical Prices", layout="wide")

st.title("Token Historical Prices in USD & EUR")
st.markdown(
    """
    Diese Webapp ruft für einen angegebenen Token (über Contract-Adresse) auf Ethereum bzw. unterstützten L2 Chains historische Preisdaten (USD) von CoinGecko ab,
    holt dazu den historischen USD/EUR-Kurs von exchangerate.host und berechnet den Tokenpreis in EUR.
    
    Zusätzlich kannst du hier optionale API Keys eingeben, falls du eigene Keys für die verwendeten APIs besitzt.
    
    Alle Daten des gewählten Jahres werden als Tabelle angezeigt und können als CSV heruntergeladen werden.
    """
)

# Mapping der unterstützten Chains zu den entsprechenden CoinGecko-IDs
chain_mapping = {
    "Ethereum": "ethereum",
    "Arbitrum": "arbitrum-one",
    "Optimism": "optimism"
}

with st.sidebar:
    st.header("Einstellungen")
    selected_chain = st.selectbox("Chain auswählen", list(chain_mapping.keys()))
    contract_address = st.text_input("Token Contract-Adresse", "").strip()
    year = st.number_input("Jahr (vollständig)", min_value=2000, max_value=2100, value=datetime.now().year, step=1)

    st.markdown("### API Keys (optional)")
    coin_gecko_api_key = st.text_input("CoinGecko API Key", type="password", help="Optional: Falls du einen eigenen API Key hast.")
    exchange_rate_api_key = st.text_input("ExchangeRate API Key", type="password", help="Optional: Falls du einen eigenen API Key hast.")

    fetch_button = st.button("Daten abrufen")

# Caching der API-Aufrufe mit st.cache_data

@st.cache_data(ttl=3600)
def fetch_token_info(chain_id: str, contract_addr: str, api_key: str = None):
    """
    Ruft Token-Informationen von CoinGecko anhand der Contract-Adresse ab.
    Falls ein API Key übergeben wird, wird er in den Headern mitgesendet.
    """
    url = f"https://api.coingecko.com/api/v3/coins/{chain_id}/contract/{contract_addr}?localization=false"
    headers = {}
    if api_key:
        headers["x-cg-pro-api-key"] = api_key  # für CoinGecko Pro
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception("Fehler beim Abruf der Token-Informationen. Bitte prüfe die Contract-Adresse, die Chain und ggf. den API Key.")
    return response.json()

@st.cache_data(ttl=3600)
def fetch_market_chart(coin_id: str, from_ts: int, to_ts: int, api_key: str = None):
    """
    Ruft historische Preisdaten von CoinGecko (in USD) für den angegebenen Zeitraum ab.
    Optional kann ein API Key übergeben werden.
    """
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart/range"
    params = {
        "vs_currency": "usd",
        "from": from_ts,
        "to": to_ts
    }
    headers = {}
    if api_key:
        headers["x-cg-pro-api-key"] = api_key
    response = requests.get(url, params=params, headers=headers)
    if response.status_code != 200:
        raise Exception("Fehler beim Abruf der Preisdaten.")
    return response.json()

@st.cache_data(ttl=86400)
def fetch_exchange_rate(date_str: str, exchange_api_key: str = None):
    """
    Ruft den historischen USD/EUR Wechselkurs für ein bestimmtes Datum ab.
    Falls ein API Key übergeben wird, wird dieser als Parameter 'access_key' mitgeschickt.
    (Hinweis: exchangerate.host benötigt in der Regel keinen API Key.)
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
    else:
        try:
            with st.spinner("Token-Informationen werden abgerufen..."):
                token_info = fetch_token_info(chain_mapping[selected_chain], contract_address, coin_gecko_api_key)
            st.success(f"Token gefunden: {token_info.get('name', 'Unbekannt')} ({token_info.get('symbol', '').upper()})")
            
            # Definiere den Zeitraum des gesamten Jahres (UTC)
            start_dt = datetime(year, 1, 1, tzinfo=timezone.utc)
            end_dt = datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
            start_ts = int(start_dt.timestamp())
            end_ts = int(end_dt.timestamp())
            
            with st.spinner("Historische Preisdaten werden abgerufen..."):
                market_data = fetch_market_chart(token_info["id"], start_ts, end_ts, coin_gecko_api_key)
            
            if "prices" not in market_data or not market_data["prices"]:
                st.error("Es wurden keine Preisdaten gefunden.")
            else:
                # Organisiere die Preisdaten jeweils pro Tag
                daily_points = {}  # key: 'YYYY-MM-DD', value: list of tuples (datetime, price)
                for point in market_data["prices"]:
                    ts, price = point
                    dt_obj = datetime.utcfromtimestamp(ts / 1000)
                    day_str = dt_obj.strftime("%Y-%m-%d")
                    daily_points.setdefault(day_str, []).append((dt_obj, price))
                
                # Erstelle für jeden Tag des Jahres einen Eintrag
                results = []
                current_date = date(year, 1, 1)
                end_date_obj = date(year, 12, 31)
                while current_date <= end_date_obj:
                    day_str = current_date.strftime("%Y-%m-%d")
                    target_noon = datetime.combine(current_date, time(12, 0))
                    
                    if day_str in daily_points:
                        # Finde den Datenpunkt, der am nächsten zur Mittagszeit liegt
                        best_point = min(daily_points[day_str], key=lambda x: abs(x[0] - target_noon))
                        token_price_usd = best_point[1]
                    else:
                        token_price_usd = None
                    
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
                
                # CSV-Download bereitstellen
                csv_data = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="CSV herunterladen",
                    data=csv_data,
                    file_name=f"{token_info.get('symbol', 'token')}_{year}.csv",
                    mime="text/csv"
                )
                
        except Exception as e:
            st.error(f"Fehler: {e}")