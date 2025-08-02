from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from pymongo import MongoClient
import subprocess
import os
import uuid
import bcrypt

app = Flask(__name__)
app.secret_key = os.urandom(24)

# MongoDB connection
client = MongoClient("mongodb+srv://TEAM-AKIRU:TEAM-AKIRU@team-akiru.iof0m6r.mongodb.net/?retryWrites=true&w=majority&appName=TEAM-AKIRU")
db = client["terminal_website"]
users_collection = db["users"]
terminals_collection = db["terminals"]

# Helper function to check if user is logged in
def is_authenticated():
    return "user_id" in session

@app.route("/")
def index():
    if is_authenticated():
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"].encode("utf-8")
        user = users_collection.find_one({"username": username})
        if user and bcrypt.checkpw(password, user["password"]):
            session["user_id"] = str(user["_id"])
            return redirect(url_for("dashboard"))
        return render_template("login.html", error="Invalid credentials")
    return render_template("login.html")

@app.route("/signup", methods=["POST"])
def signup():
    username = request.form["username"]
    password = request.form["password"].encode("utf-8")
    if users_collection.find_one({"username": username}):
        return render_template("login.html", error="Username already exists")
    hashed = bcrypt.hashpw(password, bcrypt.gensalt())
    user_id = users_collection.insert_one({"username": username, "password": hashed}).inserted_id
    session["user_id"] = str(user_id)
    return redirect(url_for("dashboard"))

@app.route("/dashboard")
def dashboard():
    if not is_authenticated():
        return redirect(url_for("login"))
    user_id = session["user_id"]
    terminals = terminals_collection.find({"user_id": user_id})
    return render_template("dashboard.html", terminals=terminals)

@app.route("/create_terminal", methods=["POST"])
def create_terminal():
    if not is_authenticated():
        return redirect(url_for("login"))
    terminal_name = request.form["terminal_name"]
    repo_url = request.form.get("repo_url", "")
    render_string = str(uuid.uuid4())[:8]
    user_id = session["user_id"]
    terminals_collection.insert_one({
        "user_id": user_id,
        "name": terminal_name,
        "render_string": render_string,
        "status": "stopped",
        "repo_url": repo_url
    })
    return redirect(url_for("dashboard"))

@app.route("/terminal/<render_string>")
def terminal(render_string):
    if not is_authenticated():
        return redirect(url_for("login"))
    terminal = terminals_collection.find_one({"render_string": render_string, "user_id": session["user_id"]})
    if not terminal:
        return "Terminal not found", 404
    return render_template("terminal.html", terminal=terminal)

@app.route("/terminal_action/<render_string>", methods=["POST"])
def terminal_action(render_string):
    if not is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
    terminal = terminals_collection.find_one({"render_string": render_string, "user_id": session["user_id"]})
    if not terminal:
        return jsonify({"error": "Terminal not found"}), 404
    action = request.json["action"]
    terminal_path = f"/tmp/terminals/{render_string}"
    
    if action == "start":
        if not os.path.exists(terminal_path):
            os.makedirs(terminal_path)
            if terminal["repo_url"]:
                subprocess.run(["git", "clone", terminal["repo_url"], terminal_path])
        # Example: Start a process (e.g., Node.js bot)
        subprocess.run(["bash", "-c", f"cd {terminal_path} && npm install && npm start &"], check=False)
        terminals_collection.update_one({"render_string": render_string}, {"$set": {"status": "running"}})
        return jsonify({"status": "running"})
    elif action == "stop":
        # Example: Stop process (simplified, use actual process management)
        subprocess.run(["pkill", "-f", f"npm start.*{render_string}"], check=False)
        terminals_collection.update_one({"render_string": render_string}, {"$set": {"status": "stopped"}})
        return jsonify({"status": "stopped"})
    elif action == "kill":
        subprocess.run(["pkill", "-f", f"npm start.*{render_string}"], check=False)
        if os.path.exists(terminal_path):
            subprocess.run(["rm", "-rf", terminal_path])
        terminals_collection.delete_one({"render_string": render_string})
        return jsonify({"status": "killed"})
    return jsonify({"error": "Invalid action"}), 400

@app.route("/execute_command/<render_string>", methods=["POST"])
def execute_command(render_string):
    if not is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
    terminal = terminals_collection.find_one({"render_string": render_string, "user_id": session["user_id"]})
    if not terminal:
        return jsonify({"error": "Terminal not found"}), 404
    command = request.json["command"]
    terminal_path = f"/tmp/terminals/{render_string}"
    try:
        result = subprocess.run(["bash", "-c", f"cd {terminal_path} && {command}"], capture_output=True, text=True)
        return jsonify({"output": result.stdout + result.stderr})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
