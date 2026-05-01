from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests
import json
import re

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app, resources={r"/*": {"origins": "*"}})

import os
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

def extract_json(text):
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except:
            pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except:
            pass
    return None

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "login.html")

@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(app.static_folder, path)

@app.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    try:
        data = request.get_json()
        if not data:
            return jsonify({"type": "chat", "reply": "Invalid request"}), 400

        message = data.get("message", "")
        history = data.get("history", [])
        profile = data.get("profile", {})
        tasks = data.get("tasks", [])

        user_name = profile.get("user_name", "User")
        ai_name = profile.get("ai_name", "Manddle")
        interests = profile.get("interests", "general")

        tasks_list_str = ""
        if tasks:
            tasks_list_str = "Current tasks:\n" + "\n".join(
                f"#{t['number']} [{t.get('period', 'daily')}] {t['title']} ({t.get('status', 'pending')})"
                + (f" – {t['description']}" if t.get('description') else "")
                for t in tasks
            )
        else:
            tasks_list_str = "No tasks yet."

        system_prompt = f"""
You are {ai_name}, a helpful productivity assistant.

User: {user_name}
Interests: {interests}

{tasks_list_str}

IMPORTANT: The numbers (#1, #2, …) are STABLE. Use them to edit tasks.

You can respond with these JSON types:

1. Normal chat: {{"type": "chat", "reply": "..."}}

2. Create a task (default period = "daily"):
   {{"type": "task", "title": "...", "description": "...", "period": "daily/monthly/yearly", "reply": "..."}}

3. Edit ANY field of a task (title, description, period, status):
   {{"type": "edit_task", "task_number": <number>, "new_title": "...", "new_description": "...", "new_period": "daily/monthly/yearly", "new_status": "pending/completed", "reply": "..."}}
   (include only the fields you want to change)

4. Delete a task:
   {{"type": "delete_task", "task_number": <number>, "reply": "..."}}

5. Add extra info (appends to description):
   {{"type": "add_info_task", "task_number": <number>, "additional_info": "...", "reply": "..."}}

Return ONLY valid JSON.
"""

        messages = [{"role": "system", "content": system_prompt}]
        for msg in history[-10:]:
            messages.append({"role": msg["role"], "content": msg["text"]})
        messages.append({"role": "user", "content": message})

        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": "llama-3.1-8b-instant", "messages": messages},
            timeout=30
        )

        if response.status_code != 200:
            detail = response.text
            print(f"Groq error {response.status_code}: {detail}")
            return jsonify({"type": "chat", "reply": f"⚠️ AI error: {detail[:100]}"})

        result = response.json()
        ai_text = result["choices"][0]["message"]["content"]
        print("AI:", ai_text)

        parsed = extract_json(ai_text)
        if parsed and "type" in parsed:
            # Validate required fields
            if parsed["type"] == "task" and "title" not in parsed:
                parsed = {"type": "chat", "reply": parsed.get("reply", "Missing title")}
            elif parsed["type"] in ("edit_task", "delete_task", "add_info_task") and "task_number" not in parsed:
                parsed = {"type": "chat", "reply": parsed.get("reply", "Missing task number")}
            return jsonify(parsed)
        else:
            return jsonify({"type": "chat", "reply": ai_text[:500]})

    except Exception as e:
        print("Server error:", e)
        return jsonify({"type": "chat", "reply": f"⚠️ Server error: {str(e)[:100]}"})

if __name__ == "__main__":
    print("🚀 Server at http://127.0.0.1:5000")
    app.run(debug=True, host='127.0.0.1', port=5000)