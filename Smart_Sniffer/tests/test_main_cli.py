"""
Tests for Smart Sniffer CLI argument handling and session labeling.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.main import parse_cli_args


def test_baseline_mode_defaults_to_baseline_label():
    args = parse_cli_args(["--run-mode", "baseline"])
    assert args.test_type == "baseline_clean_air"


def test_monitor_mode_defaults_to_unlabeled_monitor():
    args = parse_cli_args([])
    assert args.test_type == "monitor_unlabeled"


def test_odor_test_requires_explicit_test_type():
    with pytest.raises(SystemExit):
        parse_cli_args(["--run-mode", "odor_test"])


def test_odor_test_accepts_normalized_dashed_label():
    args = parse_cli_args(["--run-mode", "odor_test", "--test-type", "body-odor"])
    assert args.test_type == "body_odor"


def test_baseline_mode_rejects_non_baseline_test_type():
    with pytest.raises(SystemExit):
        parse_cli_args(["--run-mode", "baseline", "--test-type", "smoke"])


def test_simulate_flag_is_not_supported():
    with pytest.raises(SystemExit):
        parse_cli_args(["--simulate"])
