"""Deterministic planning: all arithmetic and rules live here, not in the LLM."""
import math
from datetime import datetime


def _d(s):
    return datetime.strptime(f"{s.strip()} 2026", "%d %b %Y")


def merge(records):
    """records: list of {id, date, facts}. Later dates override earlier ones."""
    state = {"venues": {}, "unavailable": set(), "rates": [], "paid": [],
             "optional": [], "judges": {}}
    for r in sorted(records, key=lambda r: _d(r["date"])):
        f = r["facts"]
        if not f.get("relevant", True):
            continue
        for k in ("students", "team_size", "budget", "staff", "event_hours",
                  "prayer_break_min", "wheelchair_users", "service_charge_pct"):
            if k in f:
                state[k] = f[k]
        for k in ("judges", "honorarium", "judge_min_per_team", "judge_max_teams"):
            if k in f:
                state["judges"][k] = f[k]
        for v in f.get("venues", []):
            state["venues"].setdefault(v["name"], {}).update(v)
        state["unavailable"].update(f.get("unavailable_venues", []))
        for c in f.get("catering_rates", []):
            if "biryani" in c["item"].lower():
                state["rates"].append((_d(r["date"]), c["per_head"]))
        state["paid"] += f.get("paid", [])
        FOOD = ("biryani", "sandwich", "box", "catering", "meal", "per head")
        state["optional"] += [o for o in f.get("optional_requests", [])
                              if not any(w in o["item"].lower() for w in FOOD)]
    return state


def plan(state, feed_everyone=True):
    students, team = state["students"], state["team_size"]
    teams = math.ceil(students / team)
    j = state["judges"]
    attendees = students + j["judges"] + state["staff"]

    # Venue: available, big enough, step-free if anyone uses a wheelchair, cheapest
    need_ramp = state.get("wheelchair_users", 0) > 0
    ok = [v for n, v in state["venues"].items()
          if n not in state["unavailable"] and v["seats"] >= attendees
          and (v.get("step_free") or not need_ramp)]
    if not ok:
        raise ValueError("No venue satisfies capacity, step-free access and availability")
    venue = min(ok, key=lambda v: v["cost"])

    # Judging
    capacity = j["judges"] * j["judge_max_teams"]
    if capacity < teams:
        raise ValueError("Not enough judge capacity")
    per_judge = math.ceil(teams / j["judges"])

    # Catering: latest quoted biryani rate, service charge on the total
    rate = max(state["rates"])[1]
    heads = attendees if feed_everyone else students
    catering = round(heads * rate * (1 + state["service_charge_pct"] / 100))

    paid = sum(p["amount"] for p in state["paid"])
    honoraria = j["judges"] * j["honorarium"]
    core = paid + venue["cost"] + honoraria + catering
    extras, total = [], core
    for o in state["optional"]:               # add optional items only if they fit
        if total + o["cost"] <= state["budget"]:
            extras.append(o)
            total += o["cost"]
    if total > state["budget"]:
        raise ValueError("Over budget")

    return {
        "teams": teams, "attendees": attendees, "venue": venue,
        "judging": {"teams_per_judge": per_judge,
                    "minutes_per_judge": per_judge * j["judge_min_per_team"],
                    "capacity": capacity},
        "schedule": {"total_min": int(state["event_hours"] * 60),
                     "prayer_break_min": state["prayer_break_min"],
                     "working_min": int(state["event_hours"] * 60) - state["prayer_break_min"]},
        "costs": {"already_paid": paid, "venue": venue["cost"], "honoraria": honoraria,
                  "catering": catering, "catering_heads": heads, "catering_rate": rate,
                  "optional_included": extras},
        "total": total, "budget": state["budget"], "remaining": state["budget"] - total,
    }
