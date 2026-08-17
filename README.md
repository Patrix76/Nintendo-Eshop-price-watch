# Nintendo eShop price watch

Checks every watched game in **every Nintendo eShop worldwide**, converts to EUR,
and only makes noise when a game hits a new all-time low **in a shop you can
actually pay in**.

Shops are split into three tiers so a cheap price you can't buy never gets
presented as a deal:

| Tier | Shops | Can you buy? |
|---|---|---|
| `paypal` | 32 — EU + NO/CH/GB, AU, NZ | **Yes, today.** Alerts come only from here |
| `paypal_new` | US, CA, MX | PayPal yes, but the Americas region is untested |
| `giftcard` | JP, ZA, IL, RU, AR, BR, CL, CO, PE | Only with a regional eShop gift card |

Runs automatically at **10:00 and 16:00** (WITA, Bali time).

## Daily use

```bash
cd "/Users/Patrix/Library/CloudStorage/Dropbox/CLAUDE WORK FOLDER/eshop-price-checker"
```

| Task | Command |
|---|---|
| **Live overview** | open `DASHBOARD.html` in a browser — bookmark it |
| Same thing as plain text | open `BEST-PRICES.md` |
| Find a game | `./eshop_game.py search "Metroid Prime 4"` |
| Track it | `./eshop_game.py add "Metroid Prime 4" 1` |
| Track with a target | `./eshop_game.py add "Metroid Prime 4" 1 --target 35` |
| What am I tracking? | `./eshop_game.py list` |
| **I bought it — stop** | `./eshop_game.py bought "Metroid Prime 4"` |
| Stop tracking entirely | `./eshop_game.py remove "Metroid Prime 4"` |
| Check right now | `./eshop_check.py` |
| Check without alerting | `./eshop_check.py --dry-run` |
| **Which shop wins most often?** | `./eshop_trend.py` |
| Trend for one game | `./eshop_trend.py "Minecraft"` |
| Trend over the last month | `./eshop_trend.py --days 30` |

Or just tell Claude: *"I bought Donkey Kong"* / *"also watch Metroid Prime 4"*.

## When you get an alert

You get a macOS notification, an e-mail to p.vanvoorst@me.com, and — if Claude is
open — a notification in Claude. Only on a **new all-time low**, never on routine runs.

To buy from another shop:

1. Spend or empty your eShop wallet — **you cannot change country with a balance left**.
2. Nintendo Account → change country to the winning shop.
3. **Pay with PayPal.** Every shop checked here accepts it.

## Why PayPal, and why these 33 shops

Nintendo blocks foreign credit cards per region: *"credit cards issued for the U.S.
will only work in the Nintendo eShop for North America."* PayPal is the way around
that — confirmed in practice, not just in theory: Tomodachi Life was bought from the
New Zealand shop on 2026-08-02 with a Dutch PayPal account.

So the shop list is filtered on **PayPal availability**, not card reach:

- **30 European shops** — Nintendo's own published PayPal country list: all EU
  members that have an eShop, plus Norway, Switzerland and the UK.
- **AU and NZ** — a separate Nintendo Australia announcement covers both, and NZ is
  proven by the Tomodachi purchase. These are usually the cheapest of the lot.

**South Africa is deliberately excluded.** Nintendo's generic European "add funds"
page mentions PayPal and quotes a ZAR balance cap, which reads like ZA support — it
isn't. That page is regional boilerplate. The authoritative per-country list, served
on Nintendo's *own South African site*, omits South Africa, and the ZA eShop really
does offer only credit card and eShop cards. Verified the hard way on 2026-08-03.

**US, CA and MX** also take PayPal and are checked, but they sit in the Nintendo of
America region, which you have not crossed into yet. They are ranked and shown, but
flagged as untested — if one ever wins, test it before trusting it.

**Japan, South Africa, Israel, Russia, Argentina, Brazil, Chile, Colombia and Peru**
are card-only, so they sit in the `giftcard` tier: priced and recorded every run, but
they never trigger an alert and never appear as "the best price". Japan revoked
foreign cards *and* foreign PayPal on 25 March 2025, explicitly to stop cross-region
bargain hunting. Argentina is often the cheapest shop on earth and equally unreachable.

The point of tracking them anyway is `eshop_trend.py`: if one shop turns out to be
cheapest almost every time, a single gift card for that shop pays for itself, and you
can just stay logged in there. The trend report says outright when that threshold is
met (cheapest in ≥70% of runs, and ≥€3 under the best PayPal shop).

**Hong Kong, Korea and Taiwan** run their own eShops with a separate ID namespace that
has not been mapped yet. None appears on Nintendo's PayPal country lists — Korea uses
Kakao Pay — so they would land in the gift-card tier too.

## Rate limiting

Nintendo's CDN will 403 the whole IP if you hammer it. A normal run is ~45 serial
requests with a pause between each, which is fine. Sweeping many countries in parallel
is not — that earned a temporary block on 2026-08-03. If a run hits a 403 it now aborts
immediately, writes nothing, alerts nothing, and logs `BLOCKED`; the next run recovers
on its own.

## Files

| File | What |
|---|---|
| `BEST-PRICES.md` | Current cheapest shop per game — rewritten each run |
| `watchlist.json` | Tracked games, IDs, targets, all-time lows |
| `eshop_check.py` | The twice-daily checker |
| `eshop_game.py` | Add / remove / mark-as-bought |
| `eshop_lib.py` | Shop lists, price API, FX, title lookup |
| `data/history.jsonl` | Every price in every shop, every run |
| `data/run.log` | What happened and when |

## Plumbing

No API keys, no accounts, no dependencies beyond system Python.

- Prices: `api.ec.nintendo.com` (Nintendo's own store API)
- Titles: Nintendo of Europe search + Nintendo of America's product index
- Rates: ECB via frankfurter.dev, with a broader feed as fallback, cached daily

Schedule: `~/Library/LaunchAgents/com.patrix.eshop-pricecheck.plist`

```bash
launchctl print gui/$(id -u)/com.patrix.eshop-pricecheck   # is it loaded?
launchctl bootout gui/$(id -u)/com.patrix.eshop-pricecheck # turn it off
```

A run missed while the Mac is asleep fires on wake. The Claude task at 10:05/16:05
re-runs the check itself if it sees the launchd run never happened.
