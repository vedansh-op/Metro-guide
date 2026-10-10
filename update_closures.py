#!/usr/bin/env python3
"""Builds closures.json using Gemini with Google Search to read today's DMRC notices.
Needs env var GEMINI_API_KEY (store it as a GitHub secret, never in the app or repo).
Optional: GEMINI_MODEL (default below). If anything fails, the old closures.json is kept."""
import json, os, re, sys, urllib.request, datetime as dt

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
HERE = os.path.dirname(os.path.abspath(__file__))
OUT, APP = os.path.join(HERE, "closures.json"), os.path.join(HERE, "index.html")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")   # VERIFY the current model name in Google AI Studio
MAX_OPEN_HOURS = 36   # an "until further notice" closure with no newer news is dropped after this
ALIASES = {"Ramakrishna Ashram Marg": "RK Ashram Marg", "Dilli Haat-INA": "INA", "Dilli Haat INA": "INA",
           "Guru Tegh Bahadur Nagar": "GTB Nagar", "Guru Teg Bahadur Nagar": "GTB Nagar",
           "Maujpur-Babarpur": "Maujpur Babarpur", "Jafrabad": "Jaffrabad", "Barakhambha Road": "Barakhamba Road"}

def station_names():
    html = open(APP, encoding="utf-8").read()
    names = set()
    for m in re.finditer(r"s:'([^']+)'", html):
        names.update(m.group(1).split(","))
    return names

def ask_gemini(names, now):
    prompt = (
        f"Now it is {now:%Y-%m-%d %H:%M} IST. Search the web for the latest official Delhi Metro (DMRC) service updates "
        "about station closures, including @OfficialDMRC posts and news reports from the last 48 hours. "
        "Work out which stations are closed for entry/exit RIGHT NOW. Newer updates override older ones; "
        "reopening or resumption updates cancel earlier closures.\n"
        'Reply with JSON only, no other text: {"closures":[{"station":"name","from":"YYYY-MM-DDTHH:MM",'
        '"until":"YYYY-MM-DDTHH:MM or null","ix":true}],"unmapped":["closed stations not in the list"]}\n'
        "Times are IST. ix=false ONLY if the notice says interchange is NOT available at that station. "
        "Use names exactly as in this list when possible: " + ", ".join(sorted(names)) +
        "\nIf no stations are closed, return an empty closures list. Never invent stations or times.")
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}], "tools": [{"google_search": {}}]}).encode()
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent", data=body,
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"], "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        resp = json.load(r)
    text = "".join(p.get("text", "") for p in resp["candidates"][0]["content"]["parts"])
    return json.loads(re.search(r"\{.*\}", text, re.S).group(0))

def main():
    now = dt.datetime.now(IST)
    names = station_names()
    res = ask_gemini(names, now)
    closures, unmapped = [], list(res.get("unmapped", []))
    for c in res.get("closures", []):
        s = ALIASES.get(c.get("station", ""), c.get("station", ""))
        if s not in names:
            unmapped.append(c.get("station", "")); continue
        frm, until = c.get("from"), c.get("until")
        if until and until < f"{now:%Y-%m-%dT%H:%M}":
            continue
        if not until and frm and (now - dt.datetime.fromisoformat(frm).replace(tzinfo=IST)).total_seconds() > MAX_OPEN_HOURS * 3600:
            continue
        closures.append({"station": s, "from": frm, "until": until, "ix": c.get("ix", True) is not False,
                         "note": "Entry and exit closed (DMRC notice)"})
    data = {"stamp": f"{now:%Y-%m-%dT%H:%M}", "updated": f"{now:%d %b %Y, %I:%M %p} IST",
            "unmapped": sorted(set(unmapped)), "closures": closures}
    json.dump(data, open(OUT, "w"), indent=1)
    print(f"{len(closures)} closed, {len(data['unmapped'])} not on map")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("Update failed, keeping old file:", e); sys.exit(1)
