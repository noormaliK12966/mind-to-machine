# Mind to Machine - Hackathon Event Planner Agent

An intelligent agent system designed for the **Mind to Machine Hackathon** to automatically plan a 4-hour physical event based on unstructured text messages (emails, WhatsApp).

The system reads a pack of messages (English and Roman Urdu), extracts planning facts, resolves conflicts chronologically, and builds a strictly verified plan covering five areas: **Venue, Schedule, Food, Judging, and Budget**.

## 🌟 Key Features

1. **LLM for Reading Only:** We use a lightweight LLM (`openai/gpt-oss-20b` via Groq) exclusively to extract facts from messy text into structured JSON. 
2. **Deterministic Engine (Zero AI Math):** All scheduling, budget calculation, and constraint verification are done using pure Python (`engine.py`). This guarantees 100% accurate math and prevents LLM hallucinations.
3. **Catching the Wrong Message:** If a new message contradicts the rules (e.g., a caterer reducing the order below the required headcount), the system rejects the message, flags it in red, and keeps the original plan valid.
4. **State Management & Updates:** The system maintains a `state.json` memory. When new messages arrive, it updates only the affected areas without starting from scratch.
5. **Full Audit Trace:** Every model call is recorded with exact token counts, inputs, outputs, and area tags, ending with a total token summary.
6. **Interactive UI:** Automatically generates a clean HTML dashboard (`out/report.html`) showing the plan, rejected messages, schedule, and the full model trace.

## 📁 Project Structure

* `run.py`: The main orchestrator. Reads input files, manages state, and coordinates between the AI and the engine.
* `llm.py`: The only file that makes model calls. Extracts facts into strict JSON.
* `engine.py`: The core logic. Merges facts, builds the schedule, calculates the budget, and verifies constraints.
* `report.py`: Generates the HTML UI dashboard.
* `requirements.txt`: Python dependencies.
* `.env`: Stores the API key (not pushed to GitHub).

## 🚀 Setup & Installation

1. **Clone the repository:**
   ```bash
   git clone <your-repo-link>
   cd Mind-to-Machine
