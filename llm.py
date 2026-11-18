"""llm.py - the ONLY place a model is called. Every call is recorded in the trace
with the token counts exactly as the API reports them."""
import os, json, time, datetime
from dotenv import load_dotenv
from groq import Groq

load_dotenv()
MODEL = os.getenv("MODEL", "openai/gpt-oss-20b")
_client = None

SYSTEM = "You extract planning facts from event messages (English or Roman Urdu) into strict JSON. Output JSON only."

PROMPT = """Year is YEAR when a date has no year. Return one entry per numbered message, same ids:
{"messages":[{"id":1,"date":"YYYY-MM-DD or null","relevant":true,"facts":{}}]}
facts holds ONLY what that message states, using these keys:
students, staff, team_size, teams, hours (event length), budget_total, prayer_break_min, start_clock ("HH:MM"),
venues [{"name","capacity","cost","features":[short keywords],"available":true/false}],
meal_options [{"name":"short lowercase label","price":per head}],
meals_ordered (how many meals a sender says they will supply),
judges_confirmed, judge_fee, judge_min_per_team, judge_max_teams, judges_per_team, judge_late_min,
spent [{"item","amount"}] (already ordered or paid from the event budget),
requests [{"item","amount"}] (asks or quotes that nobody approved),
rules [{"area":"venue|schedule|food|judging|budget","type":"requires_feature|blackout|dietary|other","value":"one short keyword or text","start":"HH:MM","end":"HH:MM"}] for any other constraint (example: needs a projector -> type requires_feature, value projector).
Numbers are plain numbers (Rs 1,200 -> 1200). Put each hall's features on that hall.
If a message has no planning facts: relevant=false, facts={}.

MESSAGES:
"""


def client():
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"], timeout=45)
    return _client


def call(trace, area, system, user):
    t = time.time()
    kw = dict(model=MODEL, temperature=0, response_format={"type": "json_object"},
              messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    if "gpt-oss" in MODEL:                     # reasoning model: keep thinking short to save tokens
        kw["reasoning_effort"] = "low"
    try:
        r = client().chat.completions.create(**kw)
    except TypeError:                          # old groq package without reasoning_effort
        kw.pop("reasoning_effort", None)
        r = client().chat.completions.create(**kw)
    u = r.usage
    trace.append({"n": len(trace) + 1, "model": getattr(r, "model", None) or MODEL, "area": area,
                  "input": system + "\n\n" + user, "output": r.choices[0].message.content,
                  "in": u.prompt_tokens, "out": u.completion_tokens, "total": u.total_tokens,
                  "secs": round(time.time() - t, 2)})
    return trace[-1]["output"]


def read(trace, texts):
    """Area 'reading': turn raw messages into structured facts. One call for the whole batch."""
    prompt = PROMPT.replace("YEAR", str(datetime.date.today().year))
    body = "\n".join(f"[{i}] {t}" for i, t in enumerate(texts, 1))
    for _ in range(2):                       # one retry only if the JSON is unusable
        out = call(trace, "reading", SYSTEM, prompt + body)
        try:
            data = json.loads(out)["messages"]
            if isinstance(data, list) and data:
                return data
        except Exception:
            pass
    raise RuntimeError("reader returned unusable JSON twice")
