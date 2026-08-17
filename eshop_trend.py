#!/usr/bin/env python3
"""Which shop is consistently cheapest?

Reads every recorded run and reports how often each shop won, so you can decide
whether it is worth buying a gift card for one shop and simply staying there.

  ./eshop_trend.py              all games, all recorded history
  ./eshop_trend.py --days 30    only the last 30 days
  ./eshop_trend.py "Minecraft"  one game
"""

import collections
import datetime
import json
import os
import sys

import eshop_lib as lib

HISTORY = os.path.join(lib.DATA_DIR, "history.jsonl")

TIER_OF = {}
for _tier, _countries, _key in lib.TIERS:
    for _c in _countries:
        TIER_OF[_c] = _tier

LABEL = {
    "paypal": "PayPal",
    "paypal_new": "PayPal, Americas region untested",
    "giftcard": "gift card only",
}


def load_runs(days=None, game_filter=None):
    if not os.path.exists(HISTORY):
        return []
    cutoff = None
    if days:
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
    runs = []
    with open(HISTORY) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if cutoff and row.get("ts", "") < cutoff:
                continue
            if game_filter and game_filter.lower() not in row["game"].lower():
                continue
            runs.append(row)
    return runs


def median(values):
    values = sorted(values)
    if not values:
        return None
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2.0


def report_game(name, runs):
    print("\n%s" % name)
    print("-" * len(name))
    print("%d run(s), %s to %s" % (
        len(runs), runs[0]["ts"][:10], runs[-1]["ts"][:10]))

    wins_all = collections.Counter()
    wins_paypal = collections.Counter()
    appearances = collections.Counter()   # runs in which this shop was actually priced
    seen = collections.defaultdict(list)
    nl_prices = []
    priced_runs = 0

    for run in runs:
        prices = run.get("prices") or {}
        if not prices:
            continue
        priced_runs += 1
        for country, eur in prices.items():
            seen[country].append(eur)
            appearances[country] += 1
        if "NL" in prices:
            nl_prices.append(prices["NL"])
        wins_all[min(prices, key=prices.get)] += 1
        payable = dict((c, e) for c, e in prices.items() if TIER_OF.get(c) == "paypal")
        if payable:
            wins_paypal[min(payable, key=payable.get)] += 1

    if not priced_runs:
        print("  no price data recorded yet")
        return

    # A shop can only win a run it took part in. The shop list has grown over time,
    # so scoring every shop against every run would punish late arrivals and flatter
    # early ones. Rate each shop only over the runs where it was actually priced.
    def win_rate(country):
        return 100.0 * wins_all[country] / appearances[country]

    coverage = set(appearances.values())
    if len(coverage) > 1:
        print("  Note: shop coverage changed over time (%d-%d shops per run), so each"
              % (min(coverage), max(coverage)))
        print("        shop is scored only over the runs it took part in.")

    nl_median = median(nl_prices)
    print("\n  Cheapest shop worldwide, by how often it won:")
    ranked = sorted(wins_all, key=lambda c: (-win_rate(c), -appearances[c]))
    for country in ranked[:6]:
        med = median(seen[country])
        vs = ""
        if nl_median:
            vs = "  %+5.1f%% vs NL" % ((med - nl_median) / nl_median * 100)
        print("    %-3s won %2d of %2d runs it was in (%3.0f%%)  median %6.2f EUR%s   [%s]"
              % (country, wins_all[country], appearances[country], win_rate(country),
                 med, vs, LABEL.get(TIER_OF.get(country), "?")))

    if wins_paypal:
        best_pp = max(wins_paypal, key=lambda c: 100.0 * wins_paypal[c] / appearances[c])
        print("\n  Cheapest PayPal shop: %s won %d of %d runs (%.0f%%), median %.2f EUR"
              % (best_pp, wins_paypal[best_pp], appearances[best_pp],
                 100.0 * wins_paypal[best_pp] / appearances[best_pp],
                 median(seen[best_pp])))

    # Is a gift card worth it? Needs a real sample, not two lucky runs.
    MIN_RUNS = 10
    if not wins_paypal:
        return
    best_pp = max(wins_paypal, key=lambda c: 100.0 * wins_paypal[c] / appearances[c])
    cards = [c for c in wins_all if TIER_OF.get(c) == "giftcard" and wins_all[c]]
    if not cards:
        return
    top = max(cards, key=win_rate)
    share, gap = win_rate(top), median(seen[best_pp]) - median(seen[top])
    print("\n  -> %s is cheapest in %.0f%% of the %d runs it was in, typically %.2f EUR"
          % (top, share, appearances[top], gap))
    print("     under the best PayPal shop (%s)." % best_pp)
    if appearances[top] < MIN_RUNS:
        print("     Only %d run(s) of data - too early to call. Needs at least %d."
              % (appearances[top], MIN_RUNS))
    elif share >= 70 and gap >= 3:
        print("     Consistent enough that a %s eShop gift card would pay for itself."
              % top)
    else:
        print("     Not consistent enough to justify a gift card - keep watching.")


def main():
    args = [a for a in sys.argv[1:]]
    days = None
    if "--days" in args:
        index = args.index("--days")
        days = int(args[index + 1])
        del args[index:index + 2]
    game_filter = args[0] if args else None

    runs = load_runs(days, game_filter)
    if not runs:
        print("No history yet. The checker writes one line per game per run;")
        print("come back after it has run a few times.")
        return

    by_game = collections.OrderedDict()
    for run in runs:
        by_game.setdefault(run["game"], []).append(run)

    span = (runs[-1]["ts"][:10], runs[0]["ts"][:10])
    print("Shop trend report  (%s runs recorded)" % len(runs))
    if span[0] == span[1]:
        print("Warning: all data is from a single day - treat percentages as noise.")

    for name, game_runs in by_game.items():
        game_runs.sort(key=lambda r: r["ts"])
        report_game(name, game_runs)
    print()


if __name__ == "__main__":
    main()
