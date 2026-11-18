"""Groq call + robust JSON extraction for one message at a time."""
import json
import os

PROMPT = """You extract facts from ONE message about planning a university hackathon.
Reply with a single JSON object and nothing else. Use ONLY these keys, and omit any key
the message does not state:

{
  "relevant": true/false,            // false if the message has nothing to do with the hackathon,
                                     // its venue, food, judges, budget or participants
  "students": int, "team_size": int, "budget": int, "staff": int,
  "event_hours": number, "prayer_break_min": int,
  "venues": [{"name": str, "seats": int, "cost": int, "step_free": bool}],
  "unavailable_venues": [str],
  "wheelchair_users": int,
  "catering_rates": [{"item": str, "per_head": int}],
  "service_charge_pct": number,
  "judges": int, "honorarium": int, "judge_min_per_team": int, "judge_max_teams": int,
  "paid": [{"item": str, "amount": int}],
  "optional_requests": [{"item": str, "cost": int}]
}

Rules:
- Numbers are plain integers in Rs (no commas). The message may mix English and Urdu.
- "Only Halls 2 and 3 have ramp access" means step_free=true for those and false for the others listed.
- A library, exam or unrelated campus notice is relevant=false and has no other keys.
- A request or quote that is not approved goes in optional_requests, never in paid.
- Food or catering prices (biryani box, sandwich box, per head) go ONLY in catering_rates, never in optional_requests.
"""


def _load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv()
        return
    except ImportError:
        pass
    if os.path.exists(".env"):
        for line in open(".env", encoding="utf-8"):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)


def _parse_json(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in reply")
    return json.loads(text[start:end + 1])


def extract_facts(message, retries=3):
    _load_env()
    from groq import Groq
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    model = os.getenv("MODEL", "openai/gpt-oss-20b")

    last = None
    for attempt in range(retries):
        kwargs = dict(
            model=model,
            temperature=0,
            max_tokens=4000,   # reasoning models spend tokens thinking
            messages=[{"role": "system", "content": PROMPT},
                      {"role": "user", "content": message}],
        )
        if attempt < retries - 1:          # last attempt: no JSON mode, parse by hand
            kwargs["response_format"] = {"type": "json_object"}
        try:
            reply = client.chat.completions.create(**kwargs)
            return _parse_json(reply.choices[0].message.content)
        except Exception as e:             # json_validate_failed, bad JSON, rate limit...
            last = e
    raise RuntimeError(f"LLM extraction failed after {retries} tries: {last}")
