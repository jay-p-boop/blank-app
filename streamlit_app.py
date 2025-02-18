import streamlit as st
import requests
import pandas as pd
import time
from datetime import datetime, timedelta

# --- Konfiguration ---
COINGECKO_API_URL = "https://api.coingecko.com/api/v3"
EXCHANGERATE_API_KEY = "YOUR_API_KEY"  # Ersetze "YOUR_API_KEY" mit deinem tatsächlichen API-Schlüssel
EXCHANGERATE_API_URL = f"https://v6.exchangerate-api.com/v6/{EXCHANGERATE_API_KEY}/latest/USD"

# --- Caching ---
cache = {}

def get_cached_data(api, key, max_age_seconds):
    """Holt Daten aus dem Cache oder ruft sie ab, wenn sie fehlen oder veraltet sind."""
    now = time.time()
    if key in cache and (now - cache[key]['timestamp']) < max_age_seconds:
        return cache[key]['data']
    else:
        if api == "coingecko":
          data = fetch_coingecko_data(key)
        elif api == "exchangerate":
          data = fetch_exchangerate_data()
        else:
          return None
        if data:
            cache[key] = {'data': data, 'timestamp': now}
        return data

# --- API-Funktionen ---

def fetch_coingecko_data(token_id, vs_currency='usd', from_timestamp=None, to_timestamp=None):
    """Holt historische Preisdaten von CoinGecko."""
    params = {
        'vs_currency': vs_currency,
        'from': from_timestamp,
        'to': to_timestamp,
    }
    url = f"{COINGECKO_API_URL}/coins/{token_id}/market_chart/range"
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()  # Fehler, wenn Statuscode nicht 200 ist
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Fehler bei der CoinGecko-API-Anfrage: {e}")
        return None
    except ValueError as e:
      st.error(f"Fehler bei der CoinGecko-API-Anfrage: {e}")
      return None

def fetch_exchangerate_data():
    """Holt die neuesten Wechselkurse von ExchangeRate-API."""
    try:
        response = requests.get(EXCHANGERATE_API_URL)
        response.raise_for_status()
        data = response.json()
        if data["result"] == "success":
             return data['conversion_rates']
        else:
            st.error(f"Fehler bei der ExchangeRate-API: {data['error-type']}")
            return None

    except requests.exceptions.RequestException as e:
        st.error(f"Fehler bei der ExchangeRate-API-Anfrage: {e}")
        return None
    except ValueError as e:
        st.error(f"Fehler bei der ExchangeRate-API-Anfrage: {e}")
        return None

# --- Datenverarbeitung ---

def get_prices_for_year(token_id, year):
    """Holt und verarbeitet Preisdaten für ein ganzes Jahr."""

    #1 Tag Puffer, da API exklusive ist.
    start_date = datetime(year, 1, 1) - timedelta(days=1)
    end_date = datetime(year, 12, 31) + timedelta(days=1)

    start_timestamp = int(start_date.timestamp())
    end_timestamp = int(end_date.timestamp())

    # CoinGecko-Daten abrufen (mit Caching)
    cache_key = f"{token_id}-{year}"
    crypto_data = get_cached_data("coingecko", f"{token_id}-{start_timestamp}-{end_timestamp}", 86400)  # 24 Stunden cachen
    if crypto_data is None:
        return None

    prices = crypto_data['prices']
    df = pd.DataFrame(prices, columns=['timestamp', 'usd_price'])
    df['date'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df[(df['date'].dt.year == year)]
    df.set_index('date', inplace=True)

    # Wechselkurs-Daten abrufen (mit Caching, für den Vortag)
    exchange_rates = {}
    for index, row in df.iterrows():
      current_date = index
      exchange_rates_date = get_cached_data("exchangerate", f"exchangerate-{current_date}", 86400) # Cache für 24h
      if exchange_rates_date is not None:
        exchange_rates[current_date.strftime('%Y-%m-%d')] = exchange_rates_date

    # DataFrame erstellen und EUR-Preise berechnen
    df['eur_usd_rate'] = df.index.map(lambda x: exchange_rates.get(x.strftime('%Y-%m-%d')).get("EUR") if exchange_rates.get(x.strftime('%Y-%m-%d')) else None)
    df['eur_price'] = df['usd_price'] * df['eur_usd_rate']
    df = df[['usd_price', 'eur_usd_rate', 'eur_price']]  # Nur benötigte Spalten behalten
    df.index = df.index.strftime('%Y-%m-%d') # Index formatieren
    return df

# --- Streamlit UI ---
st.title("Krypto-Preisverlauf")

col1, col2 = st.columns(2)
with col1:
    token_id = st.text_input("Token ID (CoinGecko)", value="ethereum")
with col2:
    year = st.selectbox("Jahr", options=range(2010, datetime.now().year + 2), index=datetime.now().year - 2010)

if st.button("Daten abrufen"):
    with st.spinner("Daten werden abgerufen..."):
        df_prices = get_prices_for_year(token_id, year)

        if df_prices is not None:
            st.dataframe(df_prices)

            # CSV-Download
            csv = df_prices.to_csv(index=True)
            st.download_button(
                label="Daten als CSV herunterladen",
                data=csv,
                file_name=f"{token_id}_prices_{year}.csv",
                mime="text/csv",
            )
        else:
            st.error("Keine Daten gefunden.")
