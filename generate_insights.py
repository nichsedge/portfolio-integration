import os
import glob
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

import requests

# Constants
DATA_DIR = "data"
OUTPUT_DIR = "data"

def get_exchange_rate():
    try:
        response = requests.get('https://hexarate.paikama.co/api/rates/USD/IDR/latest', timeout=10)
        response.raise_for_status()
        data = response.json()
        return data['data']['mid']
    except Exception as e:
        print(f"Error fetching exchange rate: {e}. Fallback to 15500.")
        return 15500

EXCHANGE_RATE = get_exchange_rate()

def load_data():
    files = glob.glob(os.path.join(DATA_DIR, "*_portfolio.csv"))
    all_data = []
    
    for file in files:
        date_str = os.path.basename(file).split('_')[0]
        try:
            df = pd.read_csv(file)
            df['date'] = pd.to_datetime(date_str)
            all_data.append(df)
        except Exception as e:
            print(f"Error reading {file}: {e}")
            
    if not all_data:
        return pd.DataFrame()
        
    combined = pd.concat(all_data, ignore_index=True)
    return combined

def preprocess_data(df):
    # Convert values to numeric, coercing errors
    df['value_idr'] = pd.to_numeric(df['value_idr'], errors='coerce').fillna(0)
    df['value_usd'] = pd.to_numeric(df['value_usd'], errors='coerce').fillna(0)
    
    # Calculate total value in IDR for all assets
    # If an asset has value_idr > 0, use it. Otherwise, convert value_usd to IDR.
    df['total_value_idr'] = df.apply(
        lambda row: row['value_idr'] if row['value_idr'] > 0 else row['value_usd'] * EXCHANGE_RATE,
        axis=1
    )
    return df

def plot_value_over_time(df):
    daily_value = df.groupby('date')['total_value_idr'].sum().reset_index()
    daily_value = daily_value.sort_values('date')
    
    plt.figure(figsize=(10, 6))
    plt.plot(daily_value['date'], daily_value['total_value_idr'], marker='o', linestyle='-', linewidth=2)
    plt.title('Total Portfolio Value Over Time (in IDR)', fontsize=14)
    plt.xlabel('Date', fontsize=12)
    plt.ylabel('Value (IDR)', fontsize=12)
    plt.grid(True, linestyle='--', alpha=0.7)
    
    # Format y-axis to show millions/billions readably
    ax = plt.gca()
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, pos: f'Rp {x/1e6:,.0f}M'))
    
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'value_over_time.png'))
    plt.close()

def plot_allocation_latest(df):
    latest_date = df['date'].max()
    latest_df = df[df['date'] == latest_date]
    
    # By Category
    category_grouped = latest_df.groupby('category')['total_value_idr'].sum().sort_values(ascending=False)
    
    plt.figure(figsize=(10, 8))
    plt.pie(category_grouped, labels=category_grouped.index, autopct='%1.1f%%', startangle=140)
    plt.title(f'Asset Allocation by Category ({latest_date.strftime("%Y-%m-%d")})', fontsize=14)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'allocation_by_category.png'))
    plt.close()
    
    # By Source
    source_grouped = latest_df.groupby('source')['total_value_idr'].sum().sort_values(ascending=False)
    
    plt.figure(figsize=(10, 8))
    plt.pie(source_grouped, labels=source_grouped.index, autopct='%1.1f%%', startangle=140)
    plt.title(f'Asset Allocation by Source ({latest_date.strftime("%Y-%m-%d")})', fontsize=14)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, 'allocation_by_source.png'))
    plt.close()

def main():
    print("Loading data...")
    df = load_data()
    if df.empty:
        print("No data found.")
        return
        
    print("Preprocessing data...")
    df = preprocess_data(df)
    
    print("Generating plots...")
    plot_value_over_time(df)
    plot_allocation_latest(df)
    print("Done! Visualizations saved to artifact directory.")

if __name__ == "__main__":
    main()
