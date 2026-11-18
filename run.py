"""run.py - the one command:  python run.py <messages file>
Fresh pack -> full run. New message(s) afterwards -> update of the saved plan."""
import sys, os, re, json, hashlib
import llm, engine, report

STATE, OUT = "state.json", "out"
SECTIONS = ("headcount", "venue", "schedule", "food", "judging", "budget")


def split(text):
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]
    if len(blocks) == 1:
        lines = [l.strip() for l in blocks[0].splitlines() if l.strip()]
        if len(lines) > 1 and all(len(l) >= 30 for l in lines):
            return lines
    return blocks


def h(t):
    return hashlib.sha1(re.sub(r"\s+", " ", t).strip().lower().encode()).hexdigest()[:12]


def failed(P):
    return {k for k, v in P["checks"].items() if not v["ok"]}


def sig(P):
    return {k: json.dumps(P[k], sort_keys=True, default=str) for k in SECTIONS}


def plan_of(records):
    F, win, contrib = engine.fold([r for r in records if r["status"] == "accepted"])
    return engine.build(F), win, contrib


def text_report(state, P):
    sc = P.get("schedule") or {}
    f = lambda m: engine.fmt(m, sc.get("start_clock"))
    L = ["=" * 74, "PLAN", "=" * 74]
    if P["headcount"]:
        c = P["headcount"]
        L.append(f"PEOPLE   : {c['total']} = {c['students']} students + {c['staff']} staff + {c['judges']} judges")
    if P["venue"]:
        L.append(f"VENUE    : {P['venue']['name']} (seats {P['venue']['capacity']}) Rs {P['venue']['cost']:,}")
    if P["food"]:
        d = P["food"]
        L.append(f"FOOD     : {d['quantity']} x {d['option']} @ Rs {d['price']:,} = Rs {d['cost']:,}")
    if P["judging"]:
        j = P["judging"]
        L.append(f"JUDGING  : {j['needed']} judges ({j['confirmed']} confirmed), {j['minutes_per_team']} min/team, "
                 f"max {j['max_teams_each']} teams each, Rs {j['fee']:,} each = Rs {j['cost']:,}")
    if sc:
        L.append("SCHEDULE :")
        L += [f"   {f(s['start'])} - {f(s['end'])}  {s['label']}" for s in sc["segments"]]
        by = {}
        for s in sc["slots"]:
            by.setdefault(s["judge"], []).append(f"T{s['team']}@{f(s['start'])}")
        L.append("JUDGE ROSTER (team@start):")
        L += [f"   Judge {j}: " + ", ".join(v) for j, v in sorted(by.items())]
    if P["budget"]:
        b = P["budget"]
        L.append("BUDGET   :")
        L += [f"   {l['item']:<48}{l['amount']:>10,}" for l in b["lines"]]
        L.append(f"   {'TOTAL':<48}{b['total']:>10,}   limit {b['limit']:,}   remaining {b['remaining']:,}")
    L += ["NOTE: " + n for n in P["notes"]]
    L += ["", "CHECKS:"]
    L += [f"   [{'PASS' if v['ok'] else 'FAIL'}] {k}: {v['detail']}" for k, v in P["checks"].items()]
    L += ["", "=" * 74, "MESSAGE DECISIONS", "=" * 74]
    for r in state["records"]:
        tag = r["status"].upper() + (" (OUTDATED)" if r.get("note") else "")
        L.append(f"#{r['seq']} run {r['run']} [{tag}] {r['text'][:100]!r}")
        if r["reason"] or r.get("note"):
            L.append("      reason: " + (r["reason"] or r["note"]))
        if r.get("affected"):
            L.append("      areas changed (by code, no model call): " + ", ".join(r["affected"]))
    L += ["", "=" * 74, "TRACE (every model call)", "=" * 74]
    for e in state["trace"]:
        L.append(f"#{e['n']} | run {e.get('run', '?')} | model: {e['model']} | area: {e['area']} | "
                 f"tokens in/out/total: {e['in']}/{e['out']}/{e['total']} | {e['secs']}s")
        L += ["INPUT:", e["input"], "OUTPUT:", e["output"], "-" * 74]
    
    for run in sorted({e.get("run") for e in state["trace"]}):
        es = [e for e in state["trace"] if e.get("run") == run]
        L.append(f"   run {run}: {len(es)} call(s), areas {sorted({e['area'] for e in es})}, "
                 f"{sum(e['total'] for e in es)} tokens")
    
    ti, to = sum(e["in"] for e in state["trace"]), sum(e["out"] for e in state["trace"])
    L.append(f"TOTAL TOKENS: {ti + to} (in {ti}, out {to}) across {len(state['trace'])} model call(s)")
    
    return "\n".join(L)


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python run.py <messages file>")
    texts = split(open(sys.argv[1], encoding="utf-8-sig", errors="replace").read())
    hashes = [h(t) for t in texts]
    state = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else None
    seen = {r["hash"] for r in state["records"]} if state else set()
    if state is None or (len(texts) >= 4 and not seen.intersection(hashes)):
        state, mode = {"records": [], "trace": [], "runs": 0}, "FULL RUN"      # a fresh pack
    else:
        mode = "UPDATE"                                                       # new message(s)
    seen = {r["hash"] for r in state["records"]}
    new, dup = [], set()
    for t, x in zip(texts, hashes):
        if x not in seen and x not in dup:
            new.append((t, x))
            dup.add(x)
    state["runs"] += 1
    run, t0 = state["runs"], len(state["trace"])
    print(f"[{mode}] run {run}: {len(texts)} message(s) in file, {len(new)} new")

    if new:
        data = llm.read(state["trace"], [t for t, _ in new])
        for e in state["trace"][t0:]:
            e["run"] = run
        by_id = {int(str(m["id"]).strip()): m for m in data
                 if isinstance(m, dict) and str(m.get("id", "")).strip().isdigit()}
        maxd = max([r["dkey"] for r in state["records"]] + [""])
        for i, (t, x) in enumerate(new, 1):
            d = by_id.get(i) or (data[i - 1] if i - 1 < len(data) and isinstance(data[i - 1], dict) else {})
            dt = d.get("date") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(d.get("date") or "")) else None
            dkey = dt or maxd                      # no date -> treat as the newest message
            maxd = max(maxd, dkey)
            facts = d.get("facts") if isinstance(d.get("facts"), dict) else {}
            rec = {"seq": len(state["records"]) + 1, "text": t, "hash": x, "run": run, "date": dt,
                   "dkey": dkey, "facts": facts, "status": "accepted", "reason": "", "affected": []}
            
            if d.get("relevant") is False or not facts:
                rec.update(status="ignored", reason="irrelevant: no planning facts in it")
            else:
                before, _, _ = plan_of(state["records"])
                after, _, _ = plan_of(state["records"] + [rec])
                bad = sorted(failed(after) - failed(before))
                if bad and not failed(before):
                    # The plan was fully valid before; this message breaks it -> reject.
                    rec.update(status="rejected", reason="would break the plan -> " +
                               " | ".join(f"{k}: {after['checks'][k]['detail']}" for k in bad))
                elif mode == "UPDATE":
                    sb, sa = sig(before), sig(after)
                    rec["affected"] = [k for k in SECTIONS if sa[k] != sb[k]]
                    
            state["records"].append(rec)

    P, win, contrib = plan_of(state["records"])
    for r in state["records"]:                    # flag messages every fact of which was overridden
        r["note"] = ""
        if r["status"] == "accepted" and contrib.get(r["seq"]):
            if not any(win.get(k) == r["seq"] for k in contrib[r["seq"]]):
                by = sorted({win[k] for k in contrib[r["seq"]]})
                r["note"] = "outdated: all its facts are overridden by newer message(s) " + \
                            ", ".join(f"#{n}" for n in by)
    os.makedirs(OUT, exist_ok=True)
    json.dump(state, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    out = text_report(state, P)
    open(f"{OUT}/final.txt", "w", encoding="utf-8").write(out)
    open(f"{OUT}/plan.json", "w", encoding="utf-8").write(json.dumps(P, ensure_ascii=False, indent=1))
    open(f"{OUT}/report.html", "w", encoding="utf-8").write(report.render(state, P))
    print(out)
    mine = [e for e in state["trace"] if e.get("run") == run]
    print(f"\nTHIS RUN: {len(mine)} model call(s), areas {sorted({e['area'] for e in mine})}, "
          f"{sum(e['total'] for e in mine)} tokens. Saved out/final.txt and out/report.html")


if __name__ == "__main__":
    main()