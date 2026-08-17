#!/usr/bin/env python3
"""Manage the watchlist.

  ./eshop_game.py search "Tomodachi Life"      list matching editions + prices
  ./eshop_game.py add "Tomodachi Life" 1       add match #1 from that list
  ./eshop_game.py add "..." 1 --target 30      ...and alert below 30 EUR
  ./eshop_game.py list                         show what is tracked
  ./eshop_game.py bought "Tomodachi Life"      stop checking - you own it now
  ./eshop_game.py remove "Tomodachi Life"      drop it entirely
"""

import datetime
import re
import sys

import eshop_lib as lib


def _key(title):
    """Normalise a title for cross-region matching: US listings carry (tm)/(r)."""
    return re.sub(r"[^a-z0-9]", "", (title or "").lower())


def find(title):
    """Match EU editions to their Americas counterpart by title."""
    eu = lib.search_eu(title)
    na = dict((_key(h["title"]), h["nsuid"]) for h in lib.search_na(title))
    for hit in eu:
        hit["na_nsuid"] = na.get(_key(hit["title"]))
    return eu


def cmd_search(title):
    hits = find(title)
    if not hits:
        print("No match for %r" % title)
        return
    rates = lib.fx_rates()
    print("\nMatches for %r:\n" % title)
    for index, hit in enumerate(hits, 1):
        prices = lib.prices_for_country(lib.HOME_COUNTRY, [hit["nsuid"]])
        price = prices.get(hit["nsuid"])
        tag = "%.2f EUR in NL" % lib.to_eur(price, rates) if price else "not sold in NL"
        print("%2d. %s" % (index, hit["title"]))
        print("    %s | released %s | %s" % (tag, hit["released"] or "?", hit["nsuid"]))
    print("\nAdd one with:  ./eshop_game.py add %r <number>\n" % title)


def cmd_add(title, choice, target=None, jp_nsuid=None):
    hits = find(title)
    if not hits:
        print("No match for %r" % title)
        return
    if not 1 <= choice <= len(hits):
        print("Pick a number between 1 and %d" % len(hits))
        return
    hit = hits[choice - 1]

    data = lib.load_watchlist()
    for game in data.setdefault("games", []):
        if game["eu_nsuid"] == hit["nsuid"]:
            print("Already tracking %s" % game["name"])
            return
    data["games"].append({
        "name": hit["title"],
        "status": "watching",
        "eu_nsuid": hit["nsuid"],
        "na_nsuid": hit.get("na_nsuid"),
        "jp_nsuid": jp_nsuid,
        "target_eur": target,
        "added": datetime.date.today().isoformat(),
        "best_seen": None,
        "url": hit.get("url"),
    })
    lib.save_watchlist(data)
    print("Now watching: %s%s" % (
        hit["title"], " (alert below %.2f EUR)" % target if target else ""))
    if not hit.get("na_nsuid"):
        print("  note: no Americas ID matched - US/CA/MX and Latin America skipped.")
    if not jp_nsuid:
        print("  note: no Japanese ID - Japan skipped. The JP search only matches")
        print("        Japanese titles, so pass it explicitly with --jp <nsuid>,")
        print("        or ask Claude to look it up.")


def cmd_list():
    games = lib.load_watchlist().get("games", [])
    if not games:
        print("Watchlist is empty.")
        return
    for game in games:
        seen = game.get("best_seen") or {}
        low = " | low %.2f EUR (%s)" % (seen["eur"], seen.get("country")) if seen.get("eur") else ""
        target = " | target %.2f EUR" % game["target_eur"] if game.get("target_eur") else ""
        print("- %-45s %-9s%s%s" % (game["name"], game.get("status", "watching"), low, target))


def _match(games, title):
    needle = title.lower()
    return [g for g in games if needle in g["name"].lower()]


def cmd_bought(title):
    data = lib.load_watchlist()
    hits = _match(data.get("games", []), title)
    if not hits:
        print("Nothing on the watchlist matches %r" % title)
        return
    for game in hits:
        game["status"] = "owned"
        game["owned_since"] = datetime.date.today().isoformat()
        print("Stopped checking %s - enjoy it." % game["name"])
    lib.save_watchlist(data)


def cmd_remove(title):
    data = lib.load_watchlist()
    hits = _match(data.get("games", []), title)
    if not hits:
        print("Nothing on the watchlist matches %r" % title)
        return
    data["games"] = [g for g in data["games"] if g not in hits]
    lib.save_watchlist(data)
    for game in hits:
        print("Removed %s" % game["name"])


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    command = args[0]
    if command == "list":
        cmd_list()
    elif command == "search" and len(args) >= 2:
        cmd_search(args[1])
    elif command == "add" and len(args) >= 3:
        target = None
        if "--target" in args:
            target = float(args[args.index("--target") + 1])
        jp_nsuid = None
        if "--jp" in args:
            jp_nsuid = args[args.index("--jp") + 1]
        cmd_add(args[1], int(args[2]), target, jp_nsuid)
    elif command == "bought" and len(args) >= 2:
        cmd_bought(args[1])
    elif command == "remove" and len(args) >= 2:
        cmd_remove(args[1])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
