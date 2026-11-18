"""Usage: python run.py pack.txt"""
import json
import os
import re
import sys

from llm import extract_facts
from planner import merge, plan
from UI import render_report

HEADER = re.compile(r"^#(\d+)\s*\|\s*From:\s*(.*?)\s*\|\s*Date:\s*(.+?)\s*$")


def parse_pack(path):
    msgs, cur = [], None
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        m = HEADER.match(line)
        if m:
            cur = {"id": int(m.group(1)), "sender": m.group(2),
                   "date": m.group(3), "text": ""}
            msgs.append(cur)
        elif line and cur:
            cur["text"] += line.strip('"') + " "
    return msgs


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: python run.py pack.txt")
    msgs = parse_pack(sys.argv[1])
    records = []
    for m in msgs:                         # one small call per message
        facts = extract_facts(f"From: {m['sender']}\nDate: {m['date']}\n{m['text']}")
        records.append({"id": m["id"], "date": m["date"], "facts": facts})
        print(f"#{m['id']:>2} relevant={facts.get('relevant', True)}")

    result = plan(merge(records))
    c = result["costs"]
    lines = [
        f"Teams: {result['teams']}   Attendees: {result['attendees']}",
        f"Venue: {result['venue']['name']} ({result['venue']['seats']} seats) Rs {c['venue']:,}",
        f"Judging: {result['judging']['teams_per_judge']} teams/judge, "
        f"{result['judging']['minutes_per_judge']} min each",
        f"Schedule: {result['schedule']['working_min']} min work + "
        f"{result['schedule']['prayer_break_min']} min prayer break",
        f"Already paid: Rs {c['already_paid']:,}",
        f"Judge honoraria: Rs {c['honoraria']:,}",
        f"Catering ({c['catering_heads']} x {c['catering_rate']} +10%): Rs {c['catering']:,}",
        "Optional included: " + (", ".join(o["item"] for o in c["optional_included"]) or "none"),
        f"TOTAL: Rs {result['total']:,} of Rs {result['budget']:,}   "
        f"Remaining: Rs {result['remaining']:,}",
    ]
    os.makedirs("out", exist_ok=True)
    json.dump(result, open("out/plan.json", "w", encoding="utf-8"), indent=2)
    open("out/final.txt", "w", encoding="utf-8").write("\n".join(lines))
    open("out/report.html", "w", encoding="utf-8").write(render_report(result))
    print("\n".join(lines))


if __name__ == "__main__":
    main()