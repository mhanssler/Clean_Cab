"""Analyze odor-class sessions against baseline readings.

This tool scans `logs/` subfolders, loads `readings_*.csv` files, and compares
sensor gas-resistance distributions for each class folder against a baseline
folder (default: `Baseline`).
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Dict, Iterable, List, Tuple


THRESHOLDS = [0.95, 0.90, 0.80, 0.70, 0.60, 0.50, 0.40, 0.30]


@dataclass
class Reading:
    timestamp: float
    temperature: float
    humidity: float
    pressure: float
    gas: float


@dataclass
class Stats:
    count: int
    duration_s: float
    gas_mean: float
    gas_median: float
    gas_std: float
    gas_min: float
    gas_p10: float
    gas_p25: float
    gas_p75: float
    gas_p90: float
    gas_max: float
    temp_mean: float
    hum_mean: float
    press_mean: float


@dataclass
class Comparison:
    label: str
    file_count: int
    reading_count: int
    median_ratio: float
    mean_ratio: float
    median_drop_pct: float
    mean_drop_pct: float
    threshold_fractions: Dict[str, float]
    threshold_counts: Dict[str, int]


def percentile(values: List[float], p: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def load_readings(csv_file: Path) -> List[Reading]:
    rows: List[Reading] = []
    with csv_file.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if (row.get("type") or "").strip() != "reading":
                continue
            if not (row.get("gas_resistance") or "").strip():
                continue
            try:
                rows.append(
                    Reading(
                        timestamp=float(row["timestamp"]),
                        temperature=float(row["temperature"]),
                        humidity=float(row["humidity"]),
                        pressure=float(row["pressure"]),
                        gas=float(row["gas_resistance"]),
                    )
                )
            except ValueError:
                continue
    return rows


def summarize(readings: List[Reading]) -> Stats:
    if not readings:
        return Stats(
            count=0,
            duration_s=0.0,
            gas_mean=float("nan"),
            gas_median=float("nan"),
            gas_std=float("nan"),
            gas_min=float("nan"),
            gas_p10=float("nan"),
            gas_p25=float("nan"),
            gas_p75=float("nan"),
            gas_p90=float("nan"),
            gas_max=float("nan"),
            temp_mean=float("nan"),
            hum_mean=float("nan"),
            press_mean=float("nan"),
        )

    gas = [r.gas for r in readings]
    temp = [r.temperature for r in readings]
    hum = [r.humidity for r in readings]
    press = [r.pressure for r in readings]
    ts = [r.timestamp for r in readings]

    return Stats(
        count=len(readings),
        duration_s=max(ts) - min(ts),
        gas_mean=mean(gas),
        gas_median=median(gas),
        gas_std=pstdev(gas) if len(gas) > 1 else 0.0,
        gas_min=min(gas),
        gas_p10=percentile(gas, 0.10),
        gas_p25=percentile(gas, 0.25),
        gas_p75=percentile(gas, 0.75),
        gas_p90=percentile(gas, 0.90),
        gas_max=max(gas),
        temp_mean=mean(temp),
        hum_mean=mean(hum),
        press_mean=mean(press),
    )


def find_csv_files(folder: Path) -> List[Path]:
    return sorted(folder.glob("readings_*.csv"))


def compare_to_baseline(label: str, stats: Stats, file_count: int, baseline_stats: Stats, readings: List[Reading]) -> Comparison:
    median_ratio = stats.gas_median / baseline_stats.gas_median
    mean_ratio = stats.gas_mean / baseline_stats.gas_mean

    ratios = [r.gas / baseline_stats.gas_median for r in readings]
    threshold_counts: Dict[str, int] = {}
    threshold_fractions: Dict[str, float] = {}
    for threshold in THRESHOLDS:
        key = f"<{threshold:.2f}"
        count = sum(1 for value in ratios if value < threshold)
        fraction = count / len(ratios) if ratios else 0.0
        threshold_counts[key] = count
        threshold_fractions[key] = fraction

    return Comparison(
        label=label,
        file_count=file_count,
        reading_count=stats.count,
        median_ratio=median_ratio,
        mean_ratio=mean_ratio,
        median_drop_pct=(1.0 - median_ratio) * 100.0,
        mean_drop_pct=(1.0 - mean_ratio) * 100.0,
        threshold_fractions=threshold_fractions,
        threshold_counts=threshold_counts,
    )


def fmt(value: float) -> str:
    return f"{value:.4f}"


def markdown_report(
    baseline_name: str,
    baseline_stats: Stats,
    comparisons: List[Comparison],
    per_folder_stats: Dict[str, Stats],
) -> str:
    ts = datetime.now().isoformat(timespec="seconds")
    lines: List[str] = []
    lines.append(f"# Baseline Comparison Report")
    lines.append("")
    lines.append(f"Generated: `{ts}`")
    lines.append("")
    lines.append(f"Baseline folder: `{baseline_name}`")
    lines.append("")
    lines.append("## Baseline Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| readings | {baseline_stats.count} |")
    lines.append(f"| duration_s | {baseline_stats.duration_s:.1f} |")
    lines.append(f"| gas_median_ohm | {baseline_stats.gas_median:.2f} |")
    lines.append(f"| gas_mean_ohm | {baseline_stats.gas_mean:.2f} |")
    lines.append(f"| gas_p10_ohm | {baseline_stats.gas_p10:.2f} |")
    lines.append(f"| gas_p90_ohm | {baseline_stats.gas_p90:.2f} |")
    lines.append(f"| humidity_mean_pct | {baseline_stats.hum_mean:.2f} |")
    lines.append("")

    lines.append("## Class vs Baseline")
    lines.append("")
    lines.append("| Class | Files | Readings | Median Ratio | Median Drop % | Mean Ratio | Mean Drop % |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for comp in comparisons:
        lines.append(
            f"| {comp.label} | {comp.file_count} | {comp.reading_count} | {comp.median_ratio:.4f} | {comp.median_drop_pct:.2f} | {comp.mean_ratio:.4f} | {comp.mean_drop_pct:.2f} |"
        )
    lines.append("")

    lines.append("## Threshold Fractions")
    lines.append("")
    header = "| Class | " + " | ".join(comp.threshold_fractions.keys()) + " |"
    sep = "|---|" + "|".join(["---:"] * len(THRESHOLDS)) + "|"
    lines.append(header)
    lines.append(sep)
    for comp in comparisons:
        values = " | ".join(f"{comp.threshold_fractions[key]:.2%}" for key in comp.threshold_fractions.keys())
        lines.append(f"| {comp.label} | {values} |")

    lines.append("")
    lines.append("## Per-Class Sensor Context")
    lines.append("")
    lines.append("| Class | temp_mean_C | hum_mean_% | press_mean_hPa | gas_median_ohm |")
    lines.append("|---|---:|---:|---:|---:|")
    for comp in comparisons:
        stats = per_folder_stats[comp.label]
        lines.append(
            f"| {comp.label} | {stats.temp_mean:.2f} | {stats.hum_mean:.2f} | {stats.press_mean:.2f} | {stats.gas_median:.2f} |"
        )

    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare odor class logs against baseline")
    parser.add_argument("--logs-root", default="logs", help="Root logs directory")
    parser.add_argument("--baseline-folder", default="Baseline", help="Baseline subfolder name")
    parser.add_argument(
        "--out-dir",
        default="",
        help="Output directory for reports (default: <logs-root>/analysis)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logs_root = Path(args.logs_root)
    if not logs_root.exists() or not logs_root.is_dir():
        raise SystemExit(f"Logs root not found: {logs_root}")

    baseline_folder = logs_root / args.baseline_folder
    baseline_files = find_csv_files(baseline_folder)
    if not baseline_files:
        raise SystemExit(f"No baseline CSV files found in: {baseline_folder}")

    baseline_readings: List[Reading] = []
    for file in baseline_files:
        baseline_readings.extend(load_readings(file))

    baseline_stats = summarize(baseline_readings)
    if baseline_stats.count == 0:
        raise SystemExit(f"No baseline reading rows found in: {baseline_folder}")

    comparisons: List[Comparison] = []
    per_folder_stats: Dict[str, Stats] = {}

    for folder in sorted(logs_root.iterdir()):
        if not folder.is_dir():
            continue
        if folder.name == args.baseline_folder or folder.name.lower() == "analysis":
            continue

        csv_files = find_csv_files(folder)
        if not csv_files:
            continue

        readings: List[Reading] = []
        for csv_file in csv_files:
            readings.extend(load_readings(csv_file))
        stats = summarize(readings)
        if stats.count == 0:
            continue

        comparison = compare_to_baseline(folder.name, stats, len(csv_files), baseline_stats, readings)
        comparisons.append(comparison)
        per_folder_stats[folder.name] = stats

    if not comparisons:
        raise SystemExit("No class folders with readings found to compare against baseline.")

    comparisons.sort(key=lambda item: item.median_ratio)

    print("Baseline folder:", baseline_folder)
    print(f"Baseline files: {len(baseline_files)}  readings: {baseline_stats.count}")
    print(f"Baseline gas median: {baseline_stats.gas_median:.2f} ohm")
    print("")
    print("Class comparison (sorted by median ratio):")
    for comp in comparisons:
        print(
            f"- {comp.label:12s} files={comp.file_count:2d} readings={comp.reading_count:4d} "
            f"median_ratio={comp.median_ratio:.4f} median_drop={comp.median_drop_pct:.2f}% "
            f"frac<0.5={comp.threshold_fractions['<0.50']:.2%}"
        )

    out_dir = Path(args.out_dir) if args.out_dir else logs_root / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    md_path = out_dir / f"baseline_vs_classes_{timestamp}.md"
    json_path = out_dir / f"baseline_vs_classes_{timestamp}.json"

    report_md = markdown_report(args.baseline_folder, baseline_stats, comparisons, per_folder_stats)
    md_path.write_text(report_md, encoding="utf-8")

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "baseline_folder": args.baseline_folder,
        "baseline": baseline_stats.__dict__,
        "comparisons": [
            {
                **comp.__dict__,
                "stats": per_folder_stats[comp.label].__dict__,
            }
            for comp in comparisons
        ],
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("")
    print("Wrote reports:")
    print("-", md_path)
    print("-", json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
