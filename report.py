"""report.py - the interface: turns state + plan into out/report.html (open it in a browser)."""
import html
import engine

CSS = """<style>
body{font:15px/1.5 system-ui,Segoe UI,sans-serif;margin:0;background:#f4f6fb;color:#1b2033}
header{background:#14163c;color:#fff;padding:18px 28px} h1{margin:0;font-size:22px}
main{max-width:1100px;margin:auto;padding:18px}
section{background:#fff;border-radius:10px;padding:14px 18px;margin:14px 0;box-shadow:0 1px 3px #0002}
h2{margin:0 0 8px;font-size:17px} table{border-collapse:collapse;width:100%} td,th{padding:5px 8px;border-bottom:1px solid #e5e8f0;text-align:left;vertical-align:top}
.pass{color:#0a7d33;font-weight:700}.fail{color:#c62828;font-weight:700}.warn{color:#b26a00;font-weight:700}
.rej{background:#fdecec;border-left:5px solid #c62828;padding:8px 12px;margin:8px 0;border-radius:6px}
.old{background:#fff6e0;border-left:5px solid #e0a000;padding:8px 12px;margin:8px 0;border-radius:6px}
.ok{background:#eaf7ee;border-left:5px solid #2e9e55;padding:8px 12px;margin:8px 0;border-radius:6px}
.ign{background:#eee;border-left:5px solid #999;padding:8px 12px;margin:8px 0;border-radius:6px}
pre{white-space:pre-wrap;background:#f0f2f8;padding:8px;border-radius:6px;font-size:12px;max-height:320px;overflow:auto}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px}.card{background:#f0f2f8;border-radius:8px;padding:10px}
small{color:#555}</style>"""


def render(state, P):
    E = html.escape
    sc = P.get("schedule") or {}
    f = lambda m: engine.fmt(m, sc.get("start_clock"))
    allok = all(v["ok"] for v in P["checks"].values())
    ti, to = sum(e["in"] for e in state["trace"]), sum(e["out"] for e in state["trace"])
    o = ["<!doctype html><meta charset=utf-8><title>Mind to Machine plan</title>", CSS,
         f"<header><h1>Mind to Machine - Event Plan</h1><small>Status: "
         f"<b>{'ALL CHECKS PASS' if allok else 'SOME CHECKS FAIL'}</b> | model calls: {len(state['trace'])} | "
         f"total tokens: {ti + to}</small></header><main>"]

    rej = [r for r in state["records"] if r["status"] == "rejected"]
    o.append("<section><h2>Rejected messages</h2>")
    if rej:
        for r in rej:
            o.append(f"<div class=rej><b>#{r['seq']}</b> {E(r['text'])}<br><b>Why rejected:</b> {E(r['reason'])}</div>")
    else:
        o.append("<small>None rejected so far.</small>")
    o.append("</section>")

    o.append("<section><h2>Checks</h2><table>")
    for k, v in P["checks"].items():
        o.append(f"<tr><td class={'pass' if v['ok'] else 'fail'}>{'PASS' if v['ok'] else 'FAIL'}</td>"
                 f"<td><b>{E(k)}</b></td><td>{E(v['detail'])}</td></tr>")
    o.append("</table>" + "".join(f"<div class=old>{E(n)}</div>" for n in P["notes"]) + "</section>")

    o.append("<section><h2>Plan</h2><div class=grid>")
    if P["headcount"]:
        c = P["headcount"]
        o.append(f"<div class=card><b>People</b><br>{c['total']}<br><small>{c['students']} students + "
                 f"{c['staff']} staff + {c['judges']} judges</small></div>")
    if P["venue"]:
        o.append(f"<div class=card><b>Venue</b><br>{E(str(P['venue']['name']))}<br><small>seats "
                 f"{P['venue']['capacity']} - Rs {P['venue']['cost']:,}</small></div>")
    if P["food"]:
        d = P["food"]
        o.append(f"<div class=card><b>Food</b><br>{d['quantity']} x {E(str(d['option']))}<br>"
                 f"<small>Rs {d['price']:,} each = Rs {d['cost']:,}</small></div>")
    if P["judging"]:
        j = P["judging"]
        o.append(f"<div class=card><b>Judging</b><br>{j['needed']} judges ({j['confirmed']} confirmed)<br>"
                 f"<small>{j['minutes_per_team']} min/team, max {j['max_teams_each']} teams each, "
                 f"Rs {j['cost']:,}</small></div>")
    o.append("</div></section>")

    if sc:
        o.append("<section><h2>Schedule</h2><table><tr><th>Time</th><th>What</th></tr>")
        o += [f"<tr><td>{f(s['start'])} - {f(s['end'])}</td><td>{E(s['label'])}</td></tr>" for s in sc["segments"]]
        o.append("</table><h2 style='margin-top:12px'>Judge roster</h2><table>")
        by = {}
        for s in sc["slots"]:
            by.setdefault(s["judge"], []).append(f"T{s['team']} @ {f(s['start'])}")
        o += [f"<tr><td>Judge {j}</td><td>{E(', '.join(v))}</td></tr>" for j, v in sorted(by.items())]
        o.append("</table></section>")

    if P["budget"]:
        b = P["budget"]
        o.append("<section><h2>Budget</h2><table>")
        o += [f"<tr><td>{E(l['item'])}</td><td align=right>Rs {l['amount']:,}</td></tr>" for l in b["lines"]]
        o.append(f"<tr><th>Total</th><th align=right>Rs {b['total']:,} / Rs {b['limit']:,} "
                 f"(remaining Rs {b['remaining']:,})</th></tr></table></section>")

    o.append("<section><h2>All messages</h2>")
    for r in state["records"]:
        cls = {"accepted": "ok", "rejected": "rej", "ignored": "ign"}[r["status"]]
        if r.get("note"):
            cls = "old"
        why = r["reason"] or r.get("note") or ""
        aff = f"<br><small>areas changed by code: {', '.join(r['affected'])}</small>" if r.get("affected") else ""
        o.append(f"<div class={cls}><b>#{r['seq']} {r['status'].upper()}</b> (run {r['run']}) "
                 f"{E(r['text'])}" + (f"<br><small>{E(why)}</small>" if why else "") + aff + "</div>")
    o.append("</section>")

    o.append(f"<section><h2>Trace - every model call</h2><b>TOTAL TOKENS: {ti + to}</b> "
             f"(in {ti}, out {to}) across {len(state['trace'])} call(s)")
    for e in state["trace"]:
        o.append(f"<details><summary><b>#{e['n']}</b> run {e.get('run', '?')} | model: {E(str(e['model']))} | "
                 f"area: <b>{E(e['area'])}</b> | tokens in/out/total: {e['in']}/{e['out']}/{e['total']}</summary>"
                 f"<b>Input</b><pre>{E(e['input'])}</pre><b>Output</b><pre>{E(e['output'])}</pre></details>")
    o.append("</section></main>")
    return "\n".join(o)
