from __future__ import annotations

import argparse
import sys
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analysis.report_visuals import summarize_threshold_scores_csv, write_threshold_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Calculate anomaly threshold for target FPR.")
    parser.add_argument("--scores", required=True, type=Path, help="Path to scores.csv (record_id plus score_anomaly/score_raw column)")
    parser.add_argument("--target-fpr", type=float, default=0.01, help="Target False Positive Rate e.g. 0.01 for 1 percent")
    parser.add_argument("--out-report", required=True, type=Path, help="Path to output markdown report")
    
    args = parser.parse_args()

    summary = summarize_threshold_scores_csv(args.scores, float(args.target_fpr))
    summary = write_threshold_report(summary, args.out_report.parent, stem=args.out_report.stem)

    print(f"Target FPR: {args.target_fpr:.4f}")
    print(f"Calculated Threshold: {float(summary.get('threshold', 0.0)):.6f}")
    print(
        "Actual FPR on this set: {0:.6f} ({1}/{2})".format(
            float(summary.get('actual_fpr', 0.0) or 0.0),
            int(summary.get('flagged_records', 0) or 0),
            int(summary.get('records_scored', 0) or 0),
        )
    )
    print(f"Report written to {summary['report_md']}")
    print(f"Metadata written to {summary['report_json']}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
