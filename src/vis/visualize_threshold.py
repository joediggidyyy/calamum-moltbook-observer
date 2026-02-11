"""
Visualize anomaly threshold for Calamum Blind ML.
"""
import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd
import seaborn as sns

def visualize_threshold(input_csv: Path, threshold: float, output_file: Path) -> None:
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
        print("Error: 'score_raw' column missing.")
        sys.exit(1)

    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Style Config
    sns.set_theme(style="whitegrid")
    try:
        font_list = ['Arial', 'Segoe UI', 'DejaVu Sans', 'sans-serif']
        plt.rcParams['font.family'] = 'sans-serif'
        plt.rcParams['font.sans-serif'] = font_list
        plt.rcParams['font.monospace'] = ['Consolas', 'Courier New', 'monospace']
        plt.rcParams['mathtext.fontset'] = 'custom'
        plt.rcParams['mathtext.rm'] = 'Arial'
        plt.rcParams['mathtext.it'] = 'Arial:italic'
        plt.rcParams['mathtext.bf'] = 'Arial:bold'
    except Exception:
        pass

    # Plot
    plt.figure(figsize=(12, 6))
    
    # Histogram
    ax = sns.histplot(
        data=df, 
        x="score_raw", 
        bins=50,
        stat="count",
        log_scale=(False, True),
        element="step",
        color="skyblue",
        alpha=0.6,
        label="Benign Scores"
    )
    
    # Robust formatter
    ax.yaxis.set_major_formatter(ticker.ScalarFormatter())

    # Highlight Anomalous Region (Values < Threshold)
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    
    plt.axvline(x=threshold, color='red', linestyle='--', linewidth=2, label=f'Threshold ({threshold:.4f})')
    # Shade region to the left of threshold (anomalous)
    # Ensure min bound is reasonable
    plot_min = min(df['score_raw'].min(), xmin)
    plt.axvspan(plot_min, threshold, color='red', alpha=0.1, label='Flagged Region')

    # Calculate FPR for this threshold
    n_total = len(df)
    n_fp = (df['score_raw'] < threshold).sum()
    fpr = (n_fp / n_total) * 100
    
    plt.title(f"Threshold Impact Analysis (FPR: {fpr:.4f}%)", fontsize=14)
    plt.xlabel("Anomaly Score (Lower = More Anomalous)", fontsize=12)
    plt.ylabel("Count (Log Scale)", fontsize=12)
    
    plt.legend(loc='upper right')
    
    # Stats Text
    stats_text = (
        f"Total Samples: {n_total}\n"
        f"Threshold:     {threshold:.4f}\n"
        f"Flagged (FP):  {n_fp}\n"
        f"FPR:           {fpr:.4f}%"
    )
    
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
        print(f"Threshold plot saved to {output_file}")
    except Exception as e:
        print(f"Error saving plot: {e}")
    finally:
        plt.close()

def main():
    parser = argparse.ArgumentParser(description="Visualize Blind ML Threshold")
    parser.add_argument("input_csv", type=Path, help="Path to scores.csv")
    parser.add_argument("threshold", type=float, help="Threshold value")
    parser.add_argument("output_file", type=Path, help="Path to output .png file")
    
    args = parser.parse_args()
    visualize_threshold(args.input_csv, args.threshold, args.output_file)

if __name__ == "__main__":
    main()
