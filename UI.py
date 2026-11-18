"""Render the plan as a clean, self-contained HTML dashboard (no installs needed)."""
from html import escape as e


def _rs(n):
    return f"Rs {n:,}"


def render_report(r):
    c, j, s, v = r["costs"], r["judging"], r["schedule"], r["venue"]
    rows = [
        ("Already paid (trophies + banners)", c["already_paid"]),
        (f"Venue: {v['name']}", c["venue"]),
        (f"Judge honoraria", c["honoraria"]),
        (f"Catering ({c['catering_heads']} x Rs {c['catering_rate']} + 10%)", c["catering"]),
    ]
    for o in c["optional_included"]:
        rows.append((o["item"].title(), o["cost"]))
    pct_used = r["total"] / r["budget"] * 100

    cost_rows = "".join(
        f"<tr><td>{e(label)}</td><td class='num'>{_rs(amount)}</td>"
        f"<td><div class='bar'><span style='width:{amount / r['budget'] * 100:.1f}%'></span></div></td></tr>"
        for label, amount in rows)

    work_pct = s["working_min"] / s["total_min"] * 100
    skipped = "" if c["optional_included"] else (
        "<li>Photo booth (Rs 30,000) skipped: it does not fit in the remaining budget.</li>")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hackathon Plan</title>
<style>
  :root {{ --bg:#f5f6fa; --card:#fff; --ink:#1f2430; --mute:#6b7280; --accent:#3b5bdb; --ok:#2f9e44; --line:#e5e7ee; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#14161c; --card:#1d2029; --ink:#e8eaf0; --mute:#9aa1b2; --accent:#7c93ff; --ok:#51cf66; --line:#2b2f3b; }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font:15px/1.5 system-ui,Segoe UI,Roboto,sans-serif; background:var(--bg); color:var(--ink); }}
  main {{ max-width:960px; margin:0 auto; padding:28px 16px 48px; }}
  h1 {{ margin:0 0 4px; font-size:26px; }}
  .sub {{ color:var(--mute); margin-bottom:22px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:14px; margin-bottom:18px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:16px 18px; }}
  .label {{ color:var(--mute); font-size:12px; text-transform:uppercase; letter-spacing:.06em; }}
  .big {{ font-size:26px; font-weight:700; margin-top:4px; }}
  .ok {{ color:var(--ok); }}
  h2 {{ font-size:17px; margin:0 0 12px; }}
  table {{ width:100%; border-collapse:collapse; }}
  td {{ padding:9px 6px; border-top:1px solid var(--line); vertical-align:middle; }}
  tr:first-child td {{ border-top:none; }}
  .num {{ text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }}
  .bar {{ background:var(--line); border-radius:99px; height:8px; min-width:80px; overflow:hidden; }}
  .bar span {{ display:block; height:100%; background:var(--accent); border-radius:99px; }}
  .total td {{ font-weight:700; border-top:2px solid var(--line); }}
  .timeline {{ display:flex; height:26px; border-radius:8px; overflow:hidden; margin:10px 0 6px; }}
  .timeline .work {{ background:var(--accent); width:{work_pct:.1f}%; }}
  .timeline .pray {{ background:var(--ok); flex:1; }}
  .legend {{ color:var(--mute); font-size:13px; }}
  ul {{ margin:6px 0 0 18px; padding:0; }}
  li {{ margin:4px 0; }}
</style></head>
<body><main>
  <h1>Hackathon Plan</h1>
  <div class="sub">{r['teams']} teams &middot; {r['attendees']} people on site &middot; budget {_rs(r['budget'])}</div>

  <div class="grid">
    <div class="card"><div class="label">Venue</div><div class="big">{e(v['name'])}</div>
      <div class="legend">{v['seats']} seats &middot; step-free access</div></div>
    <div class="card"><div class="label">Total cost</div><div class="big">{_rs(r['total'])}</div>
      <div class="legend">{pct_used:.1f}% of budget</div></div>
    <div class="card"><div class="label">Remaining</div><div class="big ok">{_rs(r['remaining'])}</div>
      <div class="legend">within budget</div></div>
    <div class="card"><div class="label">Judging</div><div class="big">{j['teams_per_judge']} teams / judge</div>
      <div class="legend">{j['minutes_per_judge']} min each &middot; capacity {j['capacity']} teams</div></div>
  </div>

  <div class="card" style="margin-bottom:18px">
    <h2>Cost breakdown</h2>
    <table>
      {cost_rows}
      <tr class="total"><td>Total</td><td class="num">{_rs(r['total'])}</td><td></td></tr>
    </table>
  </div>

  <div class="card" style="margin-bottom:18px">
    <h2>Schedule ({s['total_min'] // 60} hours)</h2>
    <div class="timeline"><div class="work"></div><div class="pray"></div></div>
    <div class="legend">{s['working_min']} min hacking and judging &middot; {s['prayer_break_min']} min prayer break</div>
  </div>

  <div class="card">
    <h2>Decisions</h2>
    <ul>
      <li>{e(v['name'])} chosen: wheelchair users need step-free access, and it is the cheapest venue that qualifies and is available.</li>
      <li>Catering uses the latest quote (Rs {c['catering_rate']} per head) plus the 10% service charge.</li>
      <li>Every team can be judged: {j['capacity']} judge slots for {r['teams']} teams.</li>
      {skipped}
    </ul>
  </div>
</main></body></html>"""
