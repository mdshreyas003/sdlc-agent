"""Bootstrap statistics: fixed-seed intervals must reproduce exactly from run to run."""

import math

from whycode.eval.stats import boot, boot_diff, fmt


def test_constant_values_have_a_zero_width_interval():
    assert boot([1.0, 1.0, 1.0]) == (1.0, 1.0, 1.0)


def test_no_values_give_no_estimate():
    assert all(math.isnan(x) for x in boot([]))


def test_fixed_seed_reproduces_a_pinned_interval():
    values = [0.0, 1.0, 1.0, 0.0, 1.0, 1.0, 1.0, 0.0, 1.0, 1.0]

    assert boot(values) == (0.7, 0.4, 1.0)
    assert boot(values) == boot(values)  # every call reseeds, so tables are reproducible


def test_balanced_coin_interval_brackets_the_mean():
    mean, lo, hi = boot([0.0, 1.0] * 20)

    assert (mean, lo, hi) == (0.5, 0.35, 0.65)


def test_paired_difference_uses_only_shared_questions():
    mean, lo, hi = boot_diff({"a": 1.0, "b": 1.0}, {"a": 0.0, "b": 0.0, "c": 5.0})

    assert (mean, lo, hi) == (1.0, 1.0, 1.0)


def test_formatting():
    assert fmt((0.625, 0.5, 0.75)) == "62% [50-75]"
    assert fmt((1.25, 1.0, 1.5), kind="num") == "1.2 [1.0-1.5]"
    assert fmt((0.0123, 0.01, 0.015), kind="usd") == "$0.0123 [0.0100-0.0150]"
    assert fmt((-0.25, -0.5, 0.0), kind="diff") == "-25 pts [-50, +0]"
    assert fmt((math.nan, math.nan, math.nan)) == "-"
