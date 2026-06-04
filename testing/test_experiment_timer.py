import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import module_experiment_timer as ET


class DummyElement:
    def __init__(self, values, key):
        self.values = values
        self.key = key

    def update(self, value):
        self.values[self.key] = value


class DummyWindow:
    def __init__(self, values):
        self.values = values

    def __getitem__(self, key):
        return DummyElement(self.values, key)


def build_values(**overrides):
    values = {
        ET.ROUND_COUNT_KEY: "2",
        ET.ROUND_INTERVAL_MIN_KEY: "3",
        ET.ASSAY_TRIM_PERCENT_KEY: "10",
    }
    values.update(overrides)
    return values


def test_get_round_settings_returns_trim_percent():
    round_count, interval_seconds, trim_percent = ET.get_round_settings(build_values())
    assert round_count == 2, round_count
    assert interval_seconds == 180, interval_seconds
    assert trim_percent == 10, trim_percent


def test_empty_trim_percent_rejects_start():
    errors = ET.validate_round_settings(build_values(**{ET.ASSAY_TRIM_PERCENT_KEY: ""}))
    assert "Enter the assay trim percent." in errors, errors


def test_trim_percent_above_range_rejects_start():
    errors = ET.validate_round_settings(build_values(**{ET.ASSAY_TRIM_PERCENT_KEY: "26"}))
    assert f"Assay trim percent must be between 0 and {ET.MAX_ASSAY_TRIM_PERCENT}." in errors, errors


def test_non_numeric_trim_input_is_stripped():
    values = build_values(**{ET.ASSAY_TRIM_PERCENT_KEY: "10x"})
    window = DummyWindow(values)
    ET.check_for_digits_in_key(ET.ASSAY_TRIM_PERCENT_KEY, window, ET.ASSAY_TRIM_PERCENT_KEY, values)
    assert values[ET.ASSAY_TRIM_PERCENT_KEY] == "10", values[ET.ASSAY_TRIM_PERCENT_KEY]


def main():
    tests = [
        test_get_round_settings_returns_trim_percent,
        test_empty_trim_percent_rejects_start,
        test_trim_percent_above_range_rejects_start,
        test_non_numeric_trim_input_is_stripped,
    ]
    for test in tests:
        test()
        print(f"PASS: {test.__name__}")


if __name__ == "__main__":
    main()
