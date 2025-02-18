import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta, date, timezone, time

st.set_page_config(page_title="Token Historical Prices", layout="wide")

st.title("Token Historical Prices in USD & EUR")
st.markdown(
    """
    Diese Webapp ruft für einen angegebenen Token (über Contract-Adresse) auf Ethereum bzw. unterstützten L2 Chains historische Preisdaten (USD) von CoinGecko ab, holt dazu den historischen USD/EUR-Kurs von exchangerate.host und berechnet den Tokenpreis in EUR. Alle Daten des gewählten Jahres werden als Tabelle angezeigt und können als CSV heruntergeladen werden.
    """
)

# Mapping Chain-Auswahl zu CoinGecko-IDs
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
    fetch_button = st.button("Daten abrufen")

# Caching für API-Aufrufe (TTL in Sekunden)
@st.experimental_memo(ttl=3600)
def fetch_token_info(chain_id: str, contract_addr: str):
    """
    Ruft die Token-Informationen von CoinGecko anhand der Contract-Adresse ab.
    """
    url = f"https://api.coingecko.com/api/v3/coins/{chain_id}/contract/{contract_addr}?localization=false"
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception("Fehler beim Abruf der Token-Informationen. Stelle sicher, dass die Contract-Adresse und die Chain korrekt sind.")
    return response.json()

@st.experimental_memo(ttl=3600)
def fetch_market_chart(coin_id: str, from_ts: int, to_ts: int):
    """
    Ruft historische Preisdaten von CoinGecko (USD) für einen bestimmten Zeitraum ab.
    """
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart/range"
    params = {
        "vs_currency": "usd",
        "from": from_ts,
        "to": to_ts
    }
    response = requests.get(url, params=params)
    if response.status_code != 200:
        raise Exception("Fehler beim Abruf der Preisdaten.")
    return response.json()

@st.experimental_memo(ttl=86400)
def fetch_exchange_rate(date_str: str):
    """
    Ruft den historischen USD/EUR Wechselkurs für ein bestimmtes Datum ab.
    """
    url = f"https://api.exchangerate.host/{date_str}"
    params = {"base": "USD", "symbols": "EUR"}
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
                token_info = fetch_token_info(chain_mapping[selected_chain], contract_address)
            st.success(f"Token gefunden: {token_info.get('name', 'Unbekannt')} ({token_info.get('symbol', '').upper()})")
            
            # Erzeuge Zeitstempel für das eingegebene Jahr (UTC)
            start_dt = datetime(year, 1, 1, tzinfo=timezone.utc)
            end_dt = datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
            start_ts = int(start_dt.timestamp())
            end_ts = int(end_dt.timestamp())
            
            with st.spinner("Historische Preisdaten werden abgerufen..."):
                market_data = fetch_market_chart(token_info["id"], start_ts, end_ts)
            
            if "prices" not in market_data or not market_data["prices"]:
                st.error("Es wurden keine Preisdaten gefunden.")
            else:
                # Verarbeite die Preise zu einem Dictionary pro Tag
                daily_points = {}  # key: 'YYYY-MM-DD', value: list of tuples (datetime, price)
                for point in market_data["prices"]:
                    ts, price = point
                    dt_obj = datetime.utcfromtimestamp(ts / 1000)
                    day_str = dt_obj.strftime("%Y-%m-%d")
                    daily_points.setdefault(day_str, []).append((dt_obj, price))
                
                # Für jeden Tag des Jahres wird ein Eintrag in der Tabelle erzeugt
                results = []
                current_date = date(year, 1, 1)
                end_date_obj = date(year, 12, 31)
                while current_date <= end_date_obj:
                    day_str = current_date.strftime("%Y-%m-%d")
                    target_noon = datetime.combine(current_date, time(12, 0))
                    
                    if day_str in daily_points:
                        # Wähle den Datenpunkt, der am nächsten zum Mittag liegt
                        best_point = min(daily_points[day_str], key=lambda x: abs(x[0] - target_noon))
                        token_price_usd = best_point[1]
                    else:
                        token_price_usd = None
                    
                    usd_to_eur = fetch_exchange_rate(day_str)
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
                
                # CSV-Download
                csv_data = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="CSV herunterladen",
                    data=csv_data,
                    file_name=f"{token_info.get('symbol', 'token')}_{year}.csv",
                    mime="text/csv"
                )
                
        except Exception as e:
            st.error(f"Fehler: {e}")