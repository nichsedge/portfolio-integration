import os
import glob
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for headless environments
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

import json
import requests

# Constants
DATA_DIR = os.getenv("PORTFOLIO_DATA_DIR") or os.getenv("DATA_DIR") or "data"
OUTPUT_DIR = DATA_DIR

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
    files = sorted(glob.glob(os.path.join(DATA_DIR, "*_snapshot.json")))
    all_data = []
    
    for file in files:
        if os.path.basename(file).startswith("latest"):
            continue
        try:
            with open(file, "r", encoding="utf-8") as f:
                content = json.load(f)
            metadata = content.get("metadata", {})
            date_str = metadata.get("date") or os.path.basename(file).split('_')[0]
            holdings = content.get("holdings", [])
            if not holdings:
                continue
            df = pd.DataFrame(holdings)
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
    
    # Calculate changes
    daily_value['diff'] = daily_value['total_value_idr'].diff()
    daily_value['pct'] = daily_value['total_value_idr'].pct_change() * 100
    
    plt.figure(figsize=(12, 7))
    plt.plot(daily_value['date'], daily_value['total_value_idr'], marker='o', linestyle='-', linewidth=2, color='#2c3e50')
    plt.title('Total Portfolio Value Over Time (in IDR)', fontsize=14, fontweight='bold')
    plt.xlabel('Date', fontsize=12)
    plt.ylabel('Value (IDR)', fontsize=12)
    plt.grid(True, linestyle='--', alpha=0.4)

    def format_total_value(value):
        if value >= 1e9:
            return f"Rp {value/1e9:,.2f}B"
        if value >= 1e6:
            return f"Rp {value/1e6:,.1f}M"
        return f"Rp {value:,.0f}"

    # Annotate total value on each date
    for i in range(len(daily_value)):
        row = daily_value.iloc[i]
        date = row['date']
        val = row['total_value_idr']
        total_label = format_total_value(val)
        plt.annotate(total_label,
                     (date, val),
                     xytext=(0, -18),
                     textcoords='offset points',
                     ha='center',
                     fontsize=8,
                     color='#2c3e50',
                     bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='#bdc3c7', alpha=0.7))
    
    # Annotate changes
    for i in range(1, len(daily_value)):
        row = daily_value.iloc[i]
        date = row['date']
        val = row['total_value_idr']
        diff = row['diff']
        pct = row['pct']
        
        color = '#27ae60' if diff >= 0 else '#e74c3c'
        prefix = '+' if diff >= 0 else ''
        label = f"{prefix}{diff/1e6:,.1f}M\n({prefix}{pct:.1f}%)"
        
        plt.annotate(label, 
                     (date, val), 
                     xytext=(0, 15), 
                     textcoords='offset points', 
                     ha='center', 
                     fontsize=9, 
                     color=color,
                     fontweight='bold',
                     bbox=dict(boxstyle='round,pad=0.3', fc='white', ec=color, alpha=0.7))
    
    # Format y-axis to show millions/billions readably
    ax = plt.gca()
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, pos: f'Rp {x/1e6:,.0f}M'))
    
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, '_vis_value_over_time.png'))
    plt.close()

def plot_allocation_latest(df):
    latest_date = df['date'].max()
    latest_df = df[df['date'] == latest_date]
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 10))
    
    # 1. By Category
    category_grouped = latest_df.groupby('category')['total_value_idr'].sum().sort_values(ascending=False)
    total = category_grouped.sum()
    legend_labels = [f'{l} ({v/total:.1%})' for l, v in category_grouped.items()]
    
    wedges1, _, autotexts1 = ax1.pie(category_grouped, autopct='%1.1f%%', startangle=140)
    ax1.legend(wedges1, legend_labels, title="Categories", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))
    ax1.set_title(f'Asset Allocation by Category', fontsize=14, fontweight='bold')
    
    # 2. By Currency
    currency_grouped = latest_df.groupby('currency')['total_value_idr'].sum().sort_values(ascending=False)
    total_currency = currency_grouped.sum()
    currency_legend_labels = [f'{l} ({v/total_currency:.1%})' for l, v in currency_grouped.items()]

    wedges2, _, autotexts2 = ax2.pie(currency_grouped, autopct='%1.1f%%', startangle=140)
    ax2.legend(wedges2, currency_legend_labels, title="Currencies", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))
    ax2.set_title(f'Asset Allocation by Currency', fontsize=14, fontweight='bold')
    
    plt.suptitle(f'Portfolio Allocation ({latest_date.strftime("%Y-%m-%d")})', fontsize=18, fontweight='bold', y=0.95)
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    plt.savefig(os.path.join(OUTPUT_DIR, '_vis_allocation_latest.png'))
    plt.close()

def plot_value_over_time_by_category(df):
    # Group by date and category
    category_time = df.groupby(['date', 'category'])['total_value_idr'].sum().unstack(fill_value=0)
    
    # Ensure columns are sorted by the latest value to make the plot look better
    latest_values = category_time.iloc[-1].sort_values(ascending=False)
    category_time = category_time[latest_values.index]
    
    plt.figure(figsize=(12, 8))
    category_time.plot(kind='area', stacked=True, ax=plt.gca(), alpha=0.8)
    
    plt.title('Portfolio Value Over Time by Category (in IDR)', fontsize=14, fontweight='bold')
    plt.xlabel('Date', fontsize=12)
    plt.ylabel('Value (IDR)', fontsize=12)
    plt.grid(True, linestyle='--', alpha=0.3)
    plt.legend(title='Category', bbox_to_anchor=(1.05, 1), loc='upper left')
    
    # Format y-axis
    ax = plt.gca()
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda x, pos: f'Rp {x/1e6:,.0f}M'))
    
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, '_vis_value_over_time_by_category.png'))
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
    plot_value_over_time_by_category(df)
    print("Done! Visualizations saved to artifact directory.")

if __name__ == "__main__":
    main()
