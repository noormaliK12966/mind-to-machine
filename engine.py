"""engine.py - NO model calls here. Pure code: merge facts, build the plan, verify it.
Everything the plan needs comes from the facts the reader extracted from the messages."""
import math, re, json

# Design choices of ours (not facts from any message)
OPEN, LUNCH, CLOSE, STEP = 15, 30, 15, 5          # minutes
NUMERIC = ("students", "staff", "team_size", "teams", "hours", "budget_total", "prayer_break_min",
           "meals_ordered", "judges_confirmed", "judge_fee", "judge_min_per_team",
           "judge_max_teams", "judges_per_team", "judge_late_min")
LISTS = {"venues": "name", "meal_options": "name", "spent": "item", "requests": "item"}
MONEY = ("capacity", "cost", "price", "amount")


def num(x):
    if isinstance(x, bool) or x is None:
        return None
    try:
        v = float(x) if isinstance(x, (int, float)) else float(re.sub(r"[^\d.]", "", str(x)))
    except ValueError:
        return None
    return int(v) if v.is_integer() else v


STOP = {"bill", "bills", "cost", "costs", "fee", "fees", "payment", "payments", "total", "charge", "charges",
        "expense", "expenses", "the", "for", "of", "and", "a", "an", "rs", "new", "updated"}


def toks(s):
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w
            for w in re.findall(r"[a-z0-9]+", str(s).lower()) if w not in STOP}


def hm(s):
    m = re.match(r"\s*(\d{1,2}):(\d{2})", str(s or ""))
    return int(m[1]) * 60 + int(m[2]) if m else None


def fmt(m, s0=None):
    if s0 is None:
        return f"+{m // 60}:{m % 60:02d}"
    t = (s0 + m) % 1440
    return f"{t // 60:02d}:{t % 60:02d}"


def fold(records):
    """Merge accepted message facts, oldest date first, so the NEWEST message wins each field."""
    F = {k: {} for k in LISTS}
    F["rules"] = []
    win, contrib = {}, {}
    for rec in sorted(records, key=lambda r: (r["dkey"], r["seq"])):
        f = rec.get("facts") or {}
        keys = contrib.setdefault(rec["seq"], [])
        for k in NUMERIC:
            v = num(f.get(k))
            if v is not None:
                if k == "hours" and v > 24:
                    v = v / 60
                F[k] = v
                win[(k,)] = rec["seq"]
                keys.append((k,))
        if hm(f.get("start_clock")) is not None:
            F["start_clock"] = f["start_clock"]
            win[("start_clock",)] = rec["seq"]
            keys.append(("start_clock",))
        for k, idk in LISTS.items():
            items = f.get(k)
            for it in items if isinstance(items, list) else []:
                if not isinstance(it, dict) or not it.get(idk):
                    continue
                name = str(it[idk]).strip().lower()
                if k in ("spent", "requests"):
                    for old in F[k]:
                        if toks(name) & toks(old):
                            name = old
                            break
                clean = {a: (num(b) if a in MONEY else b) for a, b in it.items() if b not in (None, "", [])}
                clean = {a: b for a, b in clean.items() if b is not None}
                F[k][name] = {**F[k].get(name, {}), **clean}
                win[(k, name)] = rec["seq"]
                keys.append((k, name))
        rules = f.get("rules")
        for r in rules if isinstance(rules, list) else []:
            if isinstance(r, dict):
                key = ("rule", json.dumps(r, sort_keys=True))
                if r not in F["rules"]:
                    F["rules"].append(r)
                win[key] = win.get(key, rec["seq"])
                keys.append(key)
    return F, win, contrib


def make_schedule(D, prayer, needed, teams, per, mins, late, bl, mx):
    """Build a schedule. Handles judges_per_team > 1 without double-booking any team.
    Returns None if no arrangement fits inside D and the blackout windows."""
    rounds = math.ceil(teams * per / needed)
    jlen = late + rounds * mins
    hack = D - OPEN - prayer - LUNCH - CLOSE - jlen
    if hack < 30:
        return None
    for h1 in sorted(range(15, hack - 14, STEP), key=lambda x: abs(x - 0.4 * hack)):
        t, segs = 0, []
        for label, ln in (("Opening & briefing", OPEN), ("Hacking block 1", h1), ("Prayer break", prayer),
                          ("Lunch", LUNCH), ("Hacking block 2", hack - h1), ("Judging", jlen),
                          ("Closing & awards", CLOSE)):
            if ln > 0:
                segs.append({"label": label, "start": t, "end": t + ln})
                t += ln
        js = next(s["start"] for s in segs if s["label"] == "Judging")
        # Each team gets `per` slots, each in a different round, each with a different judge.
        slots = []
        team_slots = {tt: 0 for tt in range(1, teams + 1)}
        r = 0
        while sum(team_slots.values()) < teams * per:
            if r > mx:
                return None                     # would exceed max teams per judge
            round_teams = set()
            assigned = 0
            for j in range(1, needed + 1):
                cands = [tt for tt in range(1, teams + 1)
                         if team_slots[tt] < per and tt not in round_teams]
                if not cands:
                    break
                tt = min(cands, key=lambda x: (team_slots[x], x))
                round_teams.add(tt)
                team_slots[tt] += 1
                slots.append({"judge": j, "team": tt,
                              "start": js + late + r * mins,
                              "end": js + late + (r + 1) * mins})
                assigned += 1
            if assigned == 0:
                return None
            r += 1
        # Every segment (not just judging) must stay out of every blackout window.
        bad = False
        for s in segs:
            for a, b in bl:
                if s["start"] < b and s["end"] > a:
                    bad = True
                    break
            if bad:
                break
        if not bad:
            return segs, slots
    return None


def verify(D, segs, slots, prayer, mx, bl, teams, per, mins):
    """Independent check of the finished schedule (does not trust the builder)."""
    errs, t = [], 0
    for s in segs:
        if s["start"] != t:
            errs.append("gap or overlap in timeline")
        t = s["end"]
    if t != D:
        errs.append(f"timeline is {t} min but event is {D} min")
    for g in segs:                              # blackout applies to every segment
        if any(g["start"] < b and g["end"] > a for a, b in bl):
            errs.append(f"{g['label']} inside a blackout window")
    by_j, by_t = {}, {}
    for s in slots:
        by_j.setdefault(s["judge"], []).append(s)
        by_t.setdefault(s["team"], []).append(s)
        if s["end"] - s["start"] != mins:
            errs.append("judging slot length wrong")
        for g in segs:
            if g["label"] != "Judging" and s["start"] < g["end"] and s["end"] > g["start"]:
                errs.append(f"judging overlaps {g['label']}")
        if any(s["start"] < b and s["end"] > a for a, b in bl):
            errs.append("judging inside a blackout window")
    for who, grp in (("judge", by_j), ("team", by_t)):
        for k, v in grp.items():
            v = sorted(v, key=lambda s: s["start"])
            if any(v[i]["end"] > v[i + 1]["start"] for i in range(len(v) - 1)):
                errs.append(f"{who} {k} double-booked")
    if any(len(v) > mx for v in by_j.values()):
        errs.append("a judge covers more than the maximum teams")
    if len(by_t) != teams or any(len(v) != per for v in by_t.values()):
        errs.append("not every team is judged the required number of times")
    if prayer and not any(g["label"] == "Prayer break" for g in segs):
        errs.append("prayer break missing")
    if errs:
        return False, "; ".join(sorted(set(errs)))
    return True, (f"{D} min timeline is gap-free; prayer break {prayer} min with no judging in it; "
                  f"no judge or team double-booked; max {mx} teams per judge")


def build(F):
    checks, notes = {}, []
    P = {"checks": checks, "notes": notes, "headcount": None, "venue": None, "schedule": None,
         "food": None, "judging": None, "budget": None}

    def chk(name, ok, detail):
        checks[name] = {"ok": bool(ok), "detail": detail}

    G = F.get
    missing = [k for k in ("students", "team_size", "hours", "budget_total") if G(k) is None]
    if missing:
        chk("figures", False, "missing from messages: " + ", ".join(missing))
        for k in ("budget", "venue", "schedule", "judges", "food", "areas"):
            chk(k, False, "cannot plan yet")
        return P
    students, staff, hours, limit = G("students"), G("staff") or 0, G("hours"), G("budget_total")
    D = int(round(hours * 60))
    teams = math.ceil(students / G("team_size"))
    if G("teams") and G("teams") != teams:
        chk("figures", False, f"{students} students in teams of {G('team_size')} = {teams} teams, "
                              f"but a message says {G('teams')}")
    else:
        chk("figures", True, f"{students} students, {teams} teams of {G('team_size')}, {staff} staff, "
                             f"{hours} h, budget Rs {limit:,}")

    # ---- judging
    per, mx, mins = G("judges_per_team") or 1, G("judge_max_teams"), G("judge_min_per_team")
    needed, conf = None, G("judges_confirmed")
    if mx and mins:
        needed = math.ceil(teams * per / mx)
        chk("judges", conf is not None and conf >= needed,
            f"{needed} judges needed ({teams} teams x {per} judge each, max {mx} teams per judge); {conf} confirmed")
    else:
        chk("judges", False, "judging rules missing (minutes per team / max teams per judge)")
    headcount = students + staff + (needed or 0)
    P["headcount"] = {"students": students, "staff": staff, "judges": needed or 0, "total": headcount}

    # ---- venue
    req = [str(r.get("value", "")).lower() for r in F["rules"] if r.get("type") == "requires_feature"]

    def has(v, t):
        text = (" ".join(map(str, v.get("features") or [])) + " " + str(v.get("name", ""))).lower()
        return all(w in text for w in t.split())

    pool = [v for v in F["venues"].values()
            if v.get("available") is not False and v.get("capacity") is not None and v.get("cost") is not None]
    fit = [v for v in pool if v["capacity"] >= headcount and all(has(v, t) for t in req)]
    venue = min(fit, key=lambda v: v["cost"]) if fit else None
    if venue:
        P["venue"] = {"name": venue.get("name"), "capacity": venue["capacity"], "cost": venue["cost"],
                      "features": venue.get("features", [])}
        chk("venue", True, f"{venue.get('name')} seats {venue['capacity']} >= {headcount}; cheapest that fits"
            + (f" and has {', '.join(req)}" if req else ""))
    else:
        chk("venue", False, f"no available venue seats {headcount}" + (f" with {', '.join(req)}" if req else ""))

    # ---- money that is fixed before food
    fee = G("judge_fee") or 0
    judge_cost = (needed or 0) * fee
    spent = [{"item": v.get("item"), "amount": v.get("amount") or 0} for v in F["spent"].values()]
    fixed = (venue["cost"] if venue else 0) + judge_cost + sum(s["amount"] for s in spent)

    # ---- food
    opts = [{"name": o.get("name"), "price": o["price"]} for o in F["meal_options"].values()
            if o.get("price") is not None]
    diets = [str(r.get("value", "")).lower() for r in F["rules"] if r.get("type") == "dietary"]
    if diets and opts:
        m = [o for o in opts if all(any(w in str(o["name"]).lower() for w in d.split()) for d in diets)]
        if m:
            opts = m
        else:
            notes.append(f"Dietary rule {diets} has no matching priced meal option; food cannot be planned.")
            opts = []                       # do NOT fall back to general options
    ordered = G("meals_ordered")
    qty = max(headcount, ordered or 0)
    food = None
    if opts:
        # Design choice: pick the highest-priced option that fits the budget (better meal quality).
        order = sorted(opts, key=lambda o: -o["price"])
        food = next((o for o in order if fixed + qty * o["price"] <= limit),
                    min(opts, key=lambda o: o["price"]))
        P["food"] = {"option": food["name"], "price": food["price"], "quantity": qty,
                     "cost": qty * food["price"], "diet": diets}
        bad = ordered is not None and ordered < headcount
        chk("food", not bad,
            f"{ordered} meals ordered but {headcount} people to feed "
            f"({students} students + {staff} staff + {needed or 0} judges)" if bad else
            f"{qty} meals x Rs {food['price']:,} ({food['name']}) for {headcount} people")
    else:
        chk("food", False,
            f"no meal option matches dietary rule {diets}" if diets else "no priced meal option in messages")

    # ---- budget
    lines = []
    if venue:
        lines.append({"item": f"Venue: {venue.get('name')}", "amount": venue["cost"]})
    lines.append({"item": f"Judge honorarium ({needed or 0} x Rs {fee:,})", "amount": judge_cost})
    if food:
        lines.append({"item": f"Food: {food['name']} x {qty}", "amount": qty * food["price"]})
    lines += [{"item": f"Already ordered: {s['item']}", "amount": s["amount"]} for s in spent]
    total = sum(l["amount"] for l in lines)
    pending = [{"item": v.get("item"), "amount": v.get("amount")} for v in F["requests"].values()]
    P["budget"] = {"lines": lines, "total": total, "limit": limit, "remaining": limit - total,
                   "not_funded_requests": pending}
    if pending:
        notes.append("Not funded (requests with no approval): " +
                     ", ".join(f"{p['item']} Rs {p['amount']:,}" if p["amount"] else str(p["item"]) for p in pending))
    chk("budget", total <= limit, f"total Rs {total:,} vs limit Rs {limit:,}"
        + ("" if total <= limit else f" (over by Rs {total - limit:,})"))

    # ---- judging section + schedule
    if needed:
        P["judging"] = {"needed": needed, "confirmed": conf, "fee": fee, "cost": judge_cost,
                        "max_teams_each": math.ceil(teams * per / needed), "minutes_per_team": mins,
                        "late_buffer_min": G("judge_late_min") or 0}
    if needed and mins:
        late, prayer, s0 = G("judge_late_min") or 0, G("prayer_break_min") or 0, hm(G("start_clock"))
        bl = []
        for r in F["rules"]:
            if r.get("type") == "blackout":
                a, b = hm(r.get("start")), hm(r.get("end"))
                if a is None or b is None:
                    continue
                if s0 is None:
                    notes.append("A blackout window was ignored because no event start time is in the messages.")
                    continue
                bl.append((a - s0, b - s0))
        built = make_schedule(D, prayer, needed, teams, per, mins, late, bl, mx)
        if built:
            segs, slots = built
            ok, detail = verify(D, segs, slots, prayer, mx, bl, teams, per, mins)
            P["schedule"] = {"segments": segs, "slots": slots, "start_clock": s0}
            chk("schedule", ok, detail)
        else:
            chk("schedule", False, "no valid arrangement: not enough time for opening, prayer, lunch, "
                                   "judging rounds and closing inside the blackout windows")
    else:
        chk("schedule", False, "cannot schedule: judging rules missing")

    # ---- unrecognised rule types must be visible, never silently dropped
    known = {"requires_feature", "dietary", "blackout"}
    for r in F["rules"]:
        if r.get("type") not in known:
            notes.append(f"Unhandled rule type '{r.get('type')}': {r.get('value', r)}")

    gone = [a for a in ("venue", "schedule", "food", "judging", "budget") if not P[a]]
    chk("areas", not gone, "all five areas planned" if not gone else "missing: " + ", ".join(gone))
    return P