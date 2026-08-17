"""Shared helpers for the Nintendo eShop price checker.

Only shops that accept **PayPal** are checked. Nintendo blocks foreign credit
cards per region, and PayPal is the way around that - confirmed in practice:
a NL Nintendo Account switched to NZ paid with a Dutch PayPal account.

  * PAYPAL       - PayPal confirmed available. Buy from any of these.
  * PAYPAL_NEW   - PayPal available per Nintendo, but reaching them means
                   crossing into the Nintendo of America region, which has not
                   been tested yet. Shown, ranked, flagged.

Deliberately NOT checked, because they take card only and the card gets blocked:
Israel, Argentina, Brazil, Chile, Colombia, Peru. Japan takes neither foreign
cards nor PayPal since 2025.

Note the two ID namespaces do not overlap: Nintendo of Europe covers the PAYPAL
list, Nintendo of America covers PAYPAL_NEW, and each needs its own NSUID.
"""

import json
import os
import time
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
WATCHLIST = os.path.join(BASE_DIR, "watchlist.json")

# Shops that accept PayPal. The 30 European entries are Nintendo's own published
# PayPal country list, verbatim. AU and NZ come from Nintendo Australia's separate
# PayPal announcement, and NZ is proven by an actual purchase.
#
# South Africa is NOT here. Nintendo's generic European "add funds" page mentions
# PayPal and quotes a ZAR balance cap, but that page is regional boilerplate. The
# authoritative per-country list - served on Nintendo's own ZA site - omits South
# Africa, and the ZA eShop really does offer only card and eShop cards.
PAYPAL = [
    "NL", "BE", "DE", "FR", "ES", "IT", "PT", "AT", "IE", "FI", "GR", "LU",
    "SK", "SI", "EE", "LV", "LT", "MT", "CY", "HR", "BG", "RO", "HU",
    "PL", "CZ", "SE", "DK", "NO", "GB", "CH", "AU", "NZ",
]
# PayPal is offered here too, but buying means switching to the Americas region,
# which is untested. Ranked alongside the rest, flagged in the summary.
PAYPAL_NEW = ["US", "CA", "MX"]

# Every remaining shop worldwide. No PayPal - reachable only with a regional eShop
# gift card. Tracked for the trend report, never used for alerts.
GIFTCARD_EU = ["ZA", "IL", "RU"]                    # priced with the EU nsuid
GIFTCARD_NA = ["AR", "BR", "CL", "CO", "PE"]        # priced with the Americas nsuid
GIFTCARD_JP = ["JP"]                                # needs its own jp_nsuid

# (label, countries, which nsuid field to price them with)
TIERS = [
    ("paypal", PAYPAL, "eu_nsuid"),
    ("paypal_new", PAYPAL_NEW, "na_nsuid"),
    ("giftcard", GIFTCARD_EU, "eu_nsuid"),
    ("giftcard", GIFTCARD_NA, "na_nsuid"),
    ("giftcard", GIFTCARD_JP, "jp_nsuid"),
]

JP_SEARCH = "https://search.nintendo.jp/nintendo_soft/search.json"

HOME_COUNTRY = "NL"

PRICE_API = "https://api.ec.nintendo.com/v1/price"
EU_SEARCH = "https://search.nintendo-europe.com/en/select"
ALGOLIA_URL = "https://u3b6gr4ua3-dsn.algolia.net/1/indexes/store_all_products_en_us/query"
ALGOLIA_APP = "U3B6GR4UA3"
ALGOLIA_KEY = "a29c6927638bfd8cee23993e51e721c9"

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


class Blocked(Exception):
    """Nintendo's edge returned 403 - the IP is rate-limited, back off entirely."""


def _request(url, data=None, headers=None, tries=3):
    """GET/POST returning parsed JSON, with a short retry on transient errors.

    A 403 means Nintendo's CDN has throttled this IP. Retrying makes it worse, so
    it is raised immediately as Blocked and the caller aborts the whole run rather
    than quietly recording a run with no prices in it.
    """
    hdrs = dict(UA)
    if headers:
        hdrs.update(headers)
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=hdrs)
            with urllib.request.urlopen(req, timeout=25) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                raise Blocked("403 from %s - IP throttled, try again later" % url)
            last = exc
            time.sleep(1.5 * (attempt + 1))
        except Exception as exc:  # network hiccup, 5xx
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("request failed after %d tries: %s (%s)" % (tries, url, last))


# --------------------------------------------------------------------------
# Exchange rates
# --------------------------------------------------------------------------

def fx_rates():
    """EUR-based rates, cached for the day. ECB first, broader feed for the rest."""
    cache = os.path.join(DATA_DIR, "fx-%s.json" % time.strftime("%Y-%m-%d"))
    if os.path.exists(cache):
        with open(cache) as fh:
            return json.load(fh)

    rates = {"EUR": 1.0}
    try:
        rates.update(_request("https://api.frankfurter.dev/v1/latest?base=EUR")["rates"])
    except Exception:
        pass
    try:
        broad = _request("https://open.er-api.com/v6/latest/EUR")["rates"]
        for code, rate in broad.items():
            rates.setdefault(code, rate)  # ECB wins where both have it
    except Exception:
        pass
    if len(rates) < 5:
        raise RuntimeError("could not load exchange rates")

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(cache, "w") as fh:
        json.dump(rates, fh)
    return rates


# --------------------------------------------------------------------------
# Prices
# --------------------------------------------------------------------------

def prices_for_country(country, nsuids):
    """{nsuid: price dict} for one shop. The API accepts up to 50 ids per call."""
    out = {}
    nsuids = [str(n) for n in nsuids if n]
    for start in range(0, len(nsuids), 50):
        chunk = nsuids[start:start + 50]
        url = "%s?country=%s&lang=en&ids=%s" % (PRICE_API, country, ",".join(chunk))
        try:
            payload = _request(url)
        except Exception:
            continue
        for entry in payload.get("prices", []):
            if entry.get("sales_status") != "onsale":
                continue
            sale = entry.get("discount_price")
            reg = entry.get("regular_price") or {}
            active = sale or reg
            if not active.get("raw_value"):
                continue
            out[str(entry["title_id"])] = {
                "value": float(active["raw_value"]),
                "currency": active["currency"],
                "regular": float(reg["raw_value"]) if reg.get("raw_value") else None,
                "on_sale": bool(sale),
                "sale_ends": (sale or {}).get("end_datetime"),
            }
        time.sleep(0.15)  # be gentle on Nintendo's API
    return out


def to_eur(price, rates):
    rate = rates.get(price["currency"])
    if not rate:
        return None
    return round(price["value"] / rate, 2)


# --------------------------------------------------------------------------
# Title -> NSUID lookup
# --------------------------------------------------------------------------

def search_eu(title, rows=12):
    """Search Nintendo of Europe. Returns [{title, nsuid, released, url}]."""
    query = urllib.parse.urlencode({
        "q": title, "fq": "type:GAME", "rows": rows, "wt": "json",
        "fl": "title,nsuid_txt,dates_released_dts,url,publisher",
    })
    docs = _request("%s?%s" % (EU_SEARCH, query))["response"]["docs"]
    results = []
    for doc in docs:
        ids = doc.get("nsuid_txt") or []
        if not ids:
            continue
        results.append({
            "title": doc.get("title"),
            "nsuid": ids[0],
            "publisher": doc.get("publisher"),
            "released": (doc.get("dates_released_dts") or [""])[0][:10],
            "url": "https://www.nintendo.com" + (doc.get("url") or ""),
        })
    return results


def search_jp(term, rows=10):
    """Search the Japanese eShop. Only matches Japanese titles - English queries
    return nothing - so the search term has to be the localised name."""
    query = urllib.parse.urlencode({"opt_type": 1, "limit": rows, "q": term})
    payload = _request("%s?%s" % (JP_SEARCH, query))
    return [
        {"title": item.get("title"), "nsuid": str(item.get("nsuid")),
         "jpy": item.get("price")}
        for item in payload.get("result", {}).get("items", [])
        if item.get("nsuid")
    ]


def search_na(title, rows=12):
    """Search Nintendo of America. Returns [{title, nsuid}]."""
    body = json.dumps({
        "query": title, "hitsPerPage": rows,
        "attributesToRetrieve": ["title", "nsuid", "urlKey"],
    }).encode("utf-8")
    payload = _request(
        ALGOLIA_URL, data=body,
        headers={
            "X-Algolia-API-Key": ALGOLIA_KEY,
            "X-Algolia-Application-Id": ALGOLIA_APP,
            "Content-Type": "application/json",
        },
    )
    return [
        {"title": hit.get("title"), "nsuid": hit.get("nsuid")}
        for hit in payload.get("hits", []) if hit.get("nsuid")
    ]


# --------------------------------------------------------------------------
# Watchlist
# --------------------------------------------------------------------------

def load_watchlist():
    if not os.path.exists(WATCHLIST):
        return {"games": []}
    with open(WATCHLIST) as fh:
        return json.load(fh)


def save_watchlist(data):
    with open(WATCHLIST, "w") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
