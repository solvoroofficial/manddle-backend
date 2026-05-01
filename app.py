from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import json
import re
import os

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app, resources={r"/*": {"origins": "*"}})

# 🔐 Secure API key from environment
GROQ_API_KEY = os.getenv("GROQ_API_KEY")


# -------------------------
# JSON extractor (robust)
# -------------------------
def extract_json(text):
    if not text:
        return None

    # remove ```json blocks
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except:
            return None

    return None


# -------------------------
# Routes
# -------------------------
@app.route("/")
def index():
    return "Manddle backend is running!"


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(app.static_folder, path)


@app.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    try:
        data = request.get_json(silent=True) or {}

        message = data.get("message", "")
        history = data.get("history", [])
        profile = data.get("profile", {})
        tasks = data.get("tasks", [])

        user_name = profile.get("user_name", "User")
        ai_name = profile.get("ai_name", "Manddle")
        interests = profile.get("interests", "general")

        # -------------------------
        # Task context
        # -------------------------
        if tasks:
            tasks_list_str = "Current tasks:\n" + "\n".join(
                f"#{i+1} [{t.get('period','daily')}] {t.get('title','')} ({t.get('status','pending')})"
                + (f" – {t.get('description')}" if t.get('description') else "")
                for i, t in enumerate(tasks)
            )
        else:
            tasks_list_str = "No tasks yet."

        # -------------------------
        # System Prompt
        # -------------------------
        system_prompt = f"""
You are {ai_name}, a human-like productivity assistant.

User: {user_name}
Interests: {interests}

{tasks_list_str}

IMPORTANT:
- Task numbers (#1, #2...) are stable.
- Use them to edit/delete tasks.

You must ALWAYS return JSON.

Formats:

1. Chat:
{{"type": "chat", "reply": "..."}}

2. Create task:
{{"type": "task", "title": "...", "description": "...", "period": "daily/monthly/yearly", "reply": "..."}}

3. Edit task:
{{"type": "edit_task", "task_number": 1, "new_title": "...", "new_description": "...", "new_period": "daily/monthly/yearly", "new_status": "pending/completed", "reply": "..."}}

4. Delete task:
{{"type": "delete_task", "task_number": 1, "reply": "..."}}

5. Add info:
{{"type": "add_info_task", "task_number": 1, "additional_info": "...", "reply": "..."}}

NO markdown. ONLY JSON.
"""

        messages = [{"role": "system", "content": system_prompt}]

        for msg in history[-10:]:
            role = msg.get("role", "user")
            content = msg.get("text", "")
            if content:
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": message})

        # -------------------------
        # API Call
        # -------------------------
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.1-8b-instant",
                "messages": messages
            },
            timeout=40
        )

        if response.status_code != 200:
            print("Groq Error:", response.text)
            return jsonify({
                "type": "chat",
                "reply": "⚠️ AI error"
            })

        result = response.json()
        ai_text = result["choices"][0]["message"]["content"]

        print("AI RAW:", ai_text)

        parsed = extract_json(ai_text)

        if isinstance(parsed, dict) and "type" in parsed:
            return jsonify(parsed)

        return jsonify({
            "type": "chat",
            "reply": ai_text[:500]
        })

    except Exception as e:
        print("Server Error:", str(e))
        return jsonify({
            "type": "chat",
            "reply": "⚠️ Server error"
        })


# -------------------------
# 🚀 IMPORTANT: RENDER FIX
# -------------------------
if __name__ == "__main__":
    print("🚀 Starting Manddle server...")

    port = int(os.environ.get("PORT", 5000))

    app.run(host="0.0.0.0", port=port)
