"""
Plot score distributions for Calamum Blind ML.
"""
import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd
import seaborn as sns

def plot_distributions(input_csv: Path, output_file: Path) -> None:
    """Read scores and generate a distribution plot."""
    if not input_csv.exists():
        print(f"Error: Input file {input_csv} not found.")
        sys.exit(1)

    print(f"Reading scores from {input_csv}...")
    try:
        df = pd.read_csv(input_csv)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        sys.exit(1)

    if 'score_raw' not in df.columns:
        print("Error: 'score_raw' column missing from CSV.")
        sys.exit(1)

    # Prepare output directory
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Plot Style
    sns.set_theme(style="whitegrid")

    # Override Fonts for Windows compatibility (Must be AFTER set_theme)
    try:
        font_list = ['Arial', 'Segoe UI', 'DejaVu Sans', 'sans-serif']
        plt.rcParams['font.family'] = 'sans-serif'
        plt.rcParams['font.sans-serif'] = font_list
        plt.rcParams['font.monospace'] = ['Consolas', 'Courier New', 'DejaVu Sans Mono', 'monospace']
        
        # Fix MathText crashing on missing STIX/DejaVu
        plt.rcParams['mathtext.fontset'] = 'custom'
        plt.rcParams['mathtext.rm'] = 'Arial'
        plt.rcParams['mathtext.it'] = 'Arial:italic'
        plt.rcParams['mathtext.bf'] = 'Arial:bold'
    except Exception:
        pass 
    
    # 1. Histogram & KDE
    plt.figure(figsize=(12, 6))
    
    # Check for extreme skew/outliers for visualization
    # IsolationForest scores are usually bounded [-0.5, 0.5] approx
    
    ax = sns.histplot(
        data=df, 
        x="score_raw", 
        kde=True, 
        stat="count",
        log_scale=(False, True), # Log scale Y
        line_kws={"linewidth": 2}
    )

    # Force plain text formatting for log axis to avoid MathText/Font crash
    ax.yaxis.set_major_formatter(ticker.ScalarFormatter())
    
    plt.title("Anomaly Score Distribution (Log Scale Count)", fontsize=14)
    plt.xlabel("Anomaly Score (Lower = More Anomalous)", fontsize=12)
    plt.ylabel("Count (Log Scale)", fontsize=12)
    
    # Stats Annotation
    stats = df['score_raw'].describe()
    stats_text = (
        f"Count: {int(stats['count'])}\n"
        f"Mean:  {stats['mean']:.4f}\n"
        f"Std:   {stats['std']:.4f}\n"
        f"Min:   {stats['min']:.4f}\n"
        f"Max:   {stats['max']:.4f}"
    )
    
    # Place text box
    plt.text(
        0.02, 0.95, 
        stats_text, 
        transform=ax.transAxes, 
        verticalalignment='top',
        fontsize=10,
        fontfamily='monospace',
        bbox=dict(boxstyle='round', facecolor='white', alpha=0.9)
    )

    plt.subplots_adjust(left=0.1, right=0.9, top=0.9, bottom=0.1)
    
    try:
        plt.savefig(output_file)
        print(f"Distribution plot saved to {output_file}")
    except Exception as e:
        print(f"Error saving plot: {e}")
    finally:
        plt.close()

def main():
    parser = argparse.ArgumentParser(description="Plot Blind ML Score Distributions")
    parser.add_argument("input_csv", type=Path, help="Path to scores.csv")
    parser.add_argument("output_file", type=Path, help="Path to output .png file")
    
    args = parser.parse_args()
    plot_distributions(args.input_csv, args.output_file)

if __name__ == "__main__":
    main()
