#!/usr/bin/env python3
"""Daily Nintendo eShop price check.

Runs twice a day from launchd. Prices every watched game in all 34 shops an
EU credit card can pay in, converts to EUR, and only makes noise when a game
hits a new all-time low.

  --dry-run   check and print, but send no notification or e-mail
  --report    print the current summary without checking
"""

import datetime
import json
import os
import subprocess
import sys

import eshop_lib as lib

HISTORY = os.path.join(lib.DATA_DIR, "history.jsonl")
SUMMARY = os.path.join(lib.BASE_DIR, "BEST-PRICES.md")
LOG = os.path.join(lib.DATA_DIR, "run.log")
EMAIL_TO = "p.vanvoorst@me.com"

FLAG = {
    "NL": "\U0001F1F3\U0001F1F1", "BE": "\U0001F1E7\U0001F1EA", "DE": "\U0001F1E9\U0001F1EA",
    "FR": "\U0001F1EB\U0001F1F7", "ES": "\U0001F1EA\U0001F1F8", "IT": "\U0001F1EE\U0001F1F9",
    "PT": "\U0001F1F5\U0001F1F9", "AT": "\U0001F1E6\U0001F1F9", "IE": "\U0001F1EE\U0001F1EA",
    "FI": "\U0001F1EB\U0001F1EE", "GR": "\U0001F1EC\U0001F1F7", "LU": "\U0001F1F1\U0001F1FA",
    "SK": "\U0001F1F8\U0001F1F0", "SI": "\U0001F1F8\U0001F1EE", "EE": "\U0001F1EA\U0001F1EA",
    "LV": "\U0001F1F1\U0001F1FB", "LT": "\U0001F1F1\U0001F1F9", "MT": "\U0001F1F2\U0001F1F9",
    "CY": "\U0001F1E8\U0001F1FE", "HR": "\U0001F1ED\U0001F1F7", "BG": "\U0001F1E7\U0001F1EC",
    "RO": "\U0001F1F7\U0001F1F4", "HU": "\U0001F1ED\U0001F1FA", "IL": "\U0001F1EE\U0001F1F1",
    "PL": "\U0001F1F5\U0001F1F1", "CZ": "\U0001F1E8\U0001F1FF", "SE": "\U0001F1F8\U0001F1EA",
    "DK": "\U0001F1E9\U0001F1F0", "NO": "\U0001F1F3\U0001F1F4", "GB": "\U0001F1EC\U0001F1E7",
    "CH": "\U0001F1E8\U0001F1ED", "AU": "\U0001F1E6\U0001F1FA", "NZ": "\U0001F1F3\U0001F1FF",
    "ZA": "\U0001F1FF\U0001F1E6", "US": "\U0001F1FA\U0001F1F8", "CA": "\U0001F1E8\U0001F1E6",
    "MX": "\U0001F1F2\U0001F1FD", "BR": "\U0001F1E7\U0001F1F7", "AR": "\U0001F1E6\U0001F1F7",
    "CL": "\U0001F1E8\U0001F1F1", "CO": "\U0001F1E8\U0001F1F4", "PE": "\U0001F1F5\U0001F1EA",
}


def log(msg):
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = "[%s] %s" % (stamp, msg)
    print(line)
    os.makedirs(lib.DATA_DIR, exist_ok=True)
    with open(LOG, "a") as fh:
        fh.write(line + "\n")


def shop(country):
    return "%s %s" % (FLAG.get(country, ""), country)


# --------------------------------------------------------------------------

def collect(games):
    """Price every game in every shop. Returns {game_name: {country: {...}}}."""
    rates = lib.fx_rates()
    by_game = dict((g["name"], {}) for g in games)

    for tier, countries, id_key in lib.TIERS:
        wanted = dict((g[id_key], g["name"]) for g in games if g.get(id_key))
        if not wanted:
            log("skipping %s/%s - no %s on any watched game"
                % (tier, "+".join(countries), id_key))
            continue
        for country in countries:
            for nsuid, price in lib.prices_for_country(country, wanted.keys()).items():
                eur = lib.to_eur(price, rates)
                if eur is None:
                    continue
                entry = dict(price)
                entry["eur"] = eur
                entry["tier"] = tier
                by_game[wanted[nsuid]][country] = entry
        log("priced %s (%d shops: %s)" % (tier, len(countries), " ".join(countries)))
    return by_game


def best_in(shops, tier):
    candidates = [(v["eur"], c, v) for c, v in shops.items() if v["tier"] == tier]
    if not candidates:
        return None
    eur, country, entry = min(candidates, key=lambda x: x[0])
    out = dict(entry)
    out["country"] = country
    return out


def days_left(iso):
    if not iso:
        return None
    try:
        end = datetime.datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None
    return max(0, (end - datetime.datetime.utcnow()).days)


# --------------------------------------------------------------------------

def notify(title, message):
    script = 'display notification %s with title %s sound name "Glass"' % (
        json.dumps(message), json.dumps(title))
    subprocess.run(["osascript", "-e", script], check=False)


def send_mail(subject, body):
    script = '''
    tell application "Mail"
        set msg to make new outgoing message with properties {subject:%s, content:%s, visible:false}
        tell msg to make new to recipient at end of to recipients with properties {address:%s}
        send msg
    end tell
    ''' % (json.dumps(subject), json.dumps(body), json.dumps(EMAIL_TO))
    result = subprocess.run(["osascript", "-e", script],
                            capture_output=True, text=True)
    if result.returncode != 0:
        log("MAIL FAILED: %s" % result.stderr.strip())
    else:
        log("e-mail sent to %s" % EMAIL_TO)


# --------------------------------------------------------------------------

def write_summary(games, results):
    now = datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
    out = ["# Nintendo Switch eShop - Pat's Price Watch", "",
           "_Updated %s_" % now, ""]

    watching = [g for g in games if g.get("status") != "owned"]
    for game in watching:
        shops = results.get(game["name"], {})
        best = best_in(shops, "paypal")
        out.append("## %s" % game["name"])
        out.append("")
        if not best:
            out.append("_No price found in any shop this run._")
            out.append("")
            continue

        home = shops.get(lib.HOME_COUNTRY)
        line = "**%s %.2f EUR** in %s" % ("\U0001F3F7", best["eur"], shop(best["country"]))
        if home and home["eur"] > best["eur"]:
            line += " - saves **%.2f EUR** vs NL (%.2f EUR)" % (
                home["eur"] - best["eur"], home["eur"])
        out.append(line)
        if best["on_sale"]:
            left = days_left(best.get("sale_ends"))
            out.append("")
            out.append("On sale%s (normally %.2f %s)." % (
                "" if left is None else " - ends in %d day(s)" % left,
                best["regular"] or 0, best["currency"]))
        seen = game.get("best_seen") or {}
        if seen.get("eur"):
            out.append("")
            out.append("All-time low seen: %.2f EUR (%s, %s)" % (
                seen["eur"], seen.get("country", "?"), seen.get("date", "?")))

        ranked = sorted(
            [(v["eur"], c, v) for c, v in shops.items() if v["tier"] == "paypal"])[:5]
        out.append("")
        out.append("| Shop | Local | EUR |")
        out.append("|---|---|---|")
        for eur, country, entry in ranked:
            out.append("| %s | %.2f %s | %.2f |" % (
                shop(country), entry["value"], entry["currency"], eur))

        fresh = best_in(shops, "paypal_new")
        if fresh and fresh["eur"] < best["eur"]:
            out.append("")
            out.append("_%s is cheaper at %.2f EUR and takes PayPal too - but that "
                       "means switching to the Americas region, which you have not "
                       "tested yet._" % (shop(fresh["country"]), fresh["eur"]))

        card = best_in(shops, "giftcard")
        if card and card["eur"] < best["eur"]:
            out.append("")
            out.append("_Gift-card only: %s is %.2f EUR (%.2f cheaper). No PayPal "
                       "there - you would need a %s eShop card._" % (
                           shop(card["country"]), card["eur"],
                           best["eur"] - card["eur"], card["country"]))
        out.append("")

    owned = [g["name"] for g in games if g.get("status") == "owned"]
    if owned:
        out.append("---")
        out.append("")
        out.append("No longer tracked (owned): %s" % ", ".join(owned))
        out.append("")

    with open(SUMMARY, "w") as fh:
        fh.write("\n".join(out))


DASHBOARD = os.path.join(lib.BASE_DIR, "DASHBOARD.html")

TIER_BADGE = {
    "paypal": ("buy now", "ok"),
    "paypal_new": ("PayPal, region untested", "warn"),
    "giftcard": ("gift card only", "no"),
}

CSS = """
:root{--bg:#fbfbfd;--fg:#1d1d1f;--dim:#6e6e73;--line:#e3e3e8;--card:#fff;
--ok:#0a7c3e;--okbg:#e6f5ec;--warn:#8a5a00;--warnbg:#fdf3e0;--no:#8a2020;--nobg:#fbeaea;
--gold:#c8961c;--goldbg:#fdf6e0}
@media(prefers-color-scheme:dark){:root{--bg:#0f0f12;--fg:#f2f2f7;--dim:#9a9aa2;
--line:#2a2a31;--card:#18181d;--ok:#4ade80;--okbg:#0f2f1d;--warn:#fbbf24;--warnbg:#33270a;
--no:#f87171;--nobg:#331414;--gold:#e8b53c;--goldbg:#332a10}}
*{box-sizing:border-box}
body{margin:0;padding:2rem 1.25rem 4rem;background:var(--bg);color:var(--fg);
font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.wrap{max-width:1120px;margin:0 auto}
h1{font-size:1.5rem;margin:0 0 .25rem}
.sub{color:var(--dim);font-size:.875rem;margin-bottom:2rem}
/* Cards sit side by side when there is room, and stack on a narrow window. */
.games{display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));
gap:1.25rem;margin-bottom:1.5rem;align-items:start}
.game{background:var(--card);border:1px solid var(--line);border-radius:14px;
padding:1.25rem;min-width:0}
.game h2{font-size:1.125rem;margin:0 0 .3rem}
.info-link{display:inline-block;font-size:.75rem;font-weight:600;letter-spacing:.03em;
color:var(--dim);text-decoration:none;border:1px solid var(--line);border-radius:5px;
padding:.1rem .4rem;margin-bottom:.85rem}
.info-link:hover{color:var(--fg);border-color:var(--dim)}
.hero{display:flex;flex-wrap:wrap;align-items:baseline;gap:.6rem;margin-bottom:.4rem}
.price{font-size:2.25rem;font-weight:650;letter-spacing:-.02em}
.where{font-size:1.05rem;color:var(--dim)}
.save{color:var(--ok);font-weight:600;font-size:.95rem}
.note{font-size:.875rem;color:var(--dim);margin-top:.5rem}
.sale{display:inline-block;background:var(--okbg);color:var(--ok);font-weight:600;
padding:.15rem .5rem;border-radius:6px;font-size:.8rem}
details{margin-top:1rem}
summary{cursor:pointer;color:var(--dim);font-size:.875rem}
.scroll{overflow-x:auto;margin-top:.75rem}
table{border-collapse:collapse;width:100%;font-size:.875rem}
th,td{text-align:left;padding:.4rem .5rem;border-bottom:1px solid var(--line);
white-space:nowrap}
th{color:var(--dim);font-weight:500}
td.num{text-align:right;font-variant-numeric:tabular-nums}
/* Payment badges are the widest cell ("PayPal, region untested") - let them
   wrap instead of forcing the whole table into horizontal scroll. */
th:last-child,td:last-child{white-space:normal;min-width:6.5em}
/* Gold box around the best shop you can actually pay in. Cheaper gift-card shops
   can sort above it, so this marks the row that is genuinely actionable. */
tr.top td{font-weight:650;background:var(--goldbg);
border-top:2px solid var(--gold);border-bottom:2px solid var(--gold)}
tr.top td:first-child{border-left:2px solid var(--gold);
border-top-left-radius:6px;border-bottom-left-radius:6px}
tr.top td:last-child{border-right:2px solid var(--gold);
border-top-right-radius:6px;border-bottom-right-radius:6px}
.star{color:var(--gold)}
.badge{font-size:.72rem;padding:.1rem .45rem;border-radius:5px;font-weight:600}
.badge.ok{background:var(--okbg);color:var(--ok)}
.badge.warn{background:var(--warnbg);color:var(--warn)}
.badge.no{background:var(--nobg);color:var(--no)}
.how{background:var(--card);border:1px solid var(--line);border-radius:14px;
padding:1rem 1.25rem;font-size:.875rem;color:var(--dim)}
.how b{color:var(--fg)}
"""


def esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def nl_url(url):
    """Nintendo of Europe serves every locale off the same slug - swap in Dutch."""
    return url.replace("/en-gb/", "/nl-nl/") if url else url


def write_dashboard(games, results):
    now = datetime.datetime.now().strftime("%A %d %B %Y, %H:%M")
    html = ["<div class='wrap'>", "<h1>Nintendo Switch eShop &ndash; Pat&rsquo;s Price Watch</h1>",
            "<p class='sub'>Updated %s &middot; your account is set to New Zealand</p>"
            % esc(now), "<div class='games'>"]

    for game in [g for g in games if g.get("status") != "owned"]:
        shops = results.get(game["name"], {})
        best = best_in(shops, "paypal")
        html.append("<div class='game'><h2>%s</h2>" % esc(game["name"]))
        url = nl_url(game.get("url"))
        if url:
            html.append("<a class='info-link' href='%s' target='_blank' "
                        "rel='noopener'>INFO</a>" % esc(url))
        if not best:
            html.append("<p class='note'>No price found this run.</p></div>")
            continue

        home = shops.get(lib.HOME_COUNTRY)
        html.append("<div class='hero'><span class='price'>&euro;%.2f</span>"
                    "<span class='where'>%s %s</span>" % (
                        best["eur"], FLAG.get(best["country"], ""), best["country"]))
        if home and home["eur"] > best["eur"]:
            html.append("<span class='save'>save &euro;%.2f vs NL</span>"
                        % (home["eur"] - best["eur"]))
        html.append("</div>")
        html.append("<div class='note'>%.2f %s in the %s shop</div>" % (
            best["value"], esc(best["currency"]), esc(best["country"])))
        if best["on_sale"]:
            left = days_left(best.get("sale_ends"))
            html.append("<p><span class='sale'>ON SALE%s</span></p>" % (
                "" if left is None else " &middot; ends in %d day(s)" % left))

        rows = sorted((v["eur"], c, v) for c, v in shops.items())
        html.append("<details open><summary>All %d shops</summary><div class='scroll'>"
                    "<table><tr><th>#</th><th>Shop</th><th class='num'>Local</th>"
                    "<th class='num'>EUR</th><th>Payment</th></tr>" % len(rows))
        for rank, (eur, country, entry) in enumerate(rows, 1):
            label, cls = TIER_BADGE.get(entry["tier"], ("?", "no"))
            is_best = country == best["country"]
            html.append("<tr%s><td>%s</td><td>%s %s</td><td class='num'>%.2f %s</td>"
                        "<td class='num'>&euro;%.2f</td>"
                        "<td><span class='badge %s'>%s</span></td></tr>" % (
                            " class='top'" if is_best else "",
                            "<span class='star'>&#9733;</span>" if is_best else rank,
                            FLAG.get(country, ""), country,
                            entry["value"], esc(entry["currency"]), eur, cls, label))
        html.append("</table></div></details></div>")

    html.append("</div>")  # .games
    html.append("<div class='how'><b>To buy:</b> empty your eShop wallet, set your "
                "Nintendo Account country to the winning shop, pay with PayPal. "
                "Only <b>buy now</b> shops accept PayPal &mdash; <b>gift card only</b> "
                "shops need a prepaid card bought for that country.</div>")
    html.append("</div>")

    page = ("<!doctype html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Nintendo Switch eShop &ndash; Pat&rsquo;s Price Watch</title>"
            "<style>%s</style></head><body>%s</body></html>"
            % (CSS, "".join(html)))
    with open(DASHBOARD, "w") as fh:
        fh.write(page)


def main():
    dry_run = "--dry-run" in sys.argv
    data = lib.load_watchlist()
    games = [g for g in data.get("games", []) if g.get("status") != "owned"]
    if not games:
        log("watchlist is empty - nothing to check")
        return

    log("checking %d game(s)" % len(games))
    results = collect(games)

    today = datetime.date.today().isoformat()
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    drops = []

    os.makedirs(lib.DATA_DIR, exist_ok=True)
    with open(HISTORY, "a") as hist:
        for game in games:
            shops = results.get(game["name"], {})
            best = best_in(shops, "paypal")
            if not best:
                log("no price found for %s" % game["name"])
                continue

            hist.write(json.dumps({
                "ts": stamp, "game": game["name"],
                "best_eur": best["eur"], "best_country": best["country"],
                "on_sale": best["on_sale"],
                "prices": dict((c, v["eur"]) for c, v in shops.items()),
            }, ensure_ascii=False) + "\n")

            seen = game.get("best_seen") or {}
            previous = seen.get("eur")
            target = game.get("target_eur")
            is_low = previous is None or best["eur"] < previous - 0.005
            hits_target = target is not None and best["eur"] <= target

            log("%s -> %.2f EUR in %s%s" % (
                game["name"], best["eur"], best["country"],
                " (NEW LOW)" if is_low else ""))

            if is_low:
                game["best_seen"] = {
                    "eur": best["eur"], "country": best["country"],
                    "local": "%.2f %s" % (best["value"], best["currency"]),
                    "date": today,
                }
            if is_low and previous is not None or hits_target:
                drops.append((game, best, previous))

    lib.save_watchlist(data)
    write_summary(data.get("games", []), results)
    write_dashboard(data.get("games", []), results)

    if not drops:
        log("no new lows - staying quiet")
        return

    headline = drops[0]
    game, best, previous = headline
    short = "%s: %.2f EUR in %s" % (game["name"], best["eur"], best["country"])
    if previous:
        short += " (was %.2f)" % previous
    if len(drops) > 1:
        short += " +%d more" % (len(drops) - 1)

    body = ["Nintendo eShop price drop\n"]
    for game, best, previous in drops:
        body.append("%s" % game["name"])
        body.append("  Now:      %.2f EUR  (%.2f %s) in %s" % (
            best["eur"], best["value"], best["currency"], best["country"]))
        if previous:
            body.append("  Previous: %.2f EUR" % previous)
        if best["on_sale"]:
            left = days_left(best.get("sale_ends"))
            body.append("  On sale%s" % ("" if left is None else " - ends in %d day(s)" % left))
        body.append("")
    body.append("To buy: set your Nintendo Account country to %s (eShop wallet must "
                "be empty), then pay with PayPal - every shop checked accepts it."
                % drops[0][1]["country"])
    body.append("\nFull summary: %s" % SUMMARY)
    text = "\n".join(body)

    if dry_run:
        log("dry run - would alert:\n%s" % text)
        return

    notify("eShop price drop", short)
    send_mail("eShop price drop - %s" % short, text)


if __name__ == "__main__":
    try:
        main()
    except lib.Blocked as exc:
        # Nintendo throttled us. Write nothing, alert nothing, try again next run.
        log("BLOCKED: %s - skipping this run, no data written" % exc)
        sys.exit(0)
    except Exception as exc:  # never die silently inside launchd
        log("ERROR: %s" % exc)
        raise
