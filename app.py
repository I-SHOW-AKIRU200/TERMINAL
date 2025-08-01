# app.py
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
import os
import uuid
import subprocess
import threading

app = Flask(__name__)
app.secret_key = os.urandom(24)

# MongoDB configuration
app.config["MONGO_URI"] = "mongodb+srv://TEAM-AKIRU:TEAM-AKIRU@team-akiru.iof0m6r.mongodb.net/terminal_hosting?retryWrites=true&w=majority"
mongo = PyMongo(app)

# Store active terminals
active_terminals = {}

@app.route('/')
def home():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = mongo.db.users.find_one({'username': username})
        if user and check_password_hash(user['password'], password):
            session['username'] = username
            session['user_id'] = str(user['_id'])
            return redirect(url_for('dashboard'))
        
        return render_template('login.html', error='Invalid username or password')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if mongo.db.users.find_one({'username': username}):
            return render_template('signup.html', error='Username already exists')
        
        hashed_password = generate_password_hash(password)
        mongo.db.users.insert_one({
            'username': username,
            'password': hashed_password,
            'terminals': []
        })
        
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    user = mongo.db.users.find_one({'_id': session['user_id']})
    terminals = user.get('terminals', [])
    return render_template('dashboard.html', username=session['username'], terminals=terminals)

@app.route('/add_terminal', methods=['POST'])
def add_terminal():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    terminal_name = request.form.get('terminal_name')
    if not terminal_name:
        return redirect(url_for('dashboard'))
    
    terminal_id = str(uuid.uuid4())
    mongo.db.users.update_one(
        {'_id': session['user_id']},
        {'$push': {'terminals': {
            'id': terminal_id,
            'name': terminal_name,
            'status': 'stopped',
            'repo_url': '',
            'pid': None
        }}}
    )
    
    return redirect(url_for('dashboard'))

@app.route('/terminal/<terminal_id>')
def terminal(terminal_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    user = mongo.db.users.find_one({'_id': session['user_id']})
    terminal = next((t for t in user['terminals'] if t['id'] == terminal_id), None)
    
    if not terminal:
        return redirect(url_for('dashboard'))
    
    return render_template('terminal.html', terminal=terminal)

@app.route('/terminal_action', methods=['POST'])
def terminal_action():
    if 'username' not in session:
        return jsonify({'status': 'error', 'message': 'Not logged in'}), 401
    
    terminal_id = request.form.get('terminal_id')
    action = request.form.get('action')
    repo_url = request.form.get('repo_url', '')
    
    user = mongo.db.users.find_one({'_id': session['user_id']})
    terminal = next((t for t in user['terminals'] if t['id'] == terminal_id), None)
    
    if not terminal:
        return jsonify({'status': 'error', 'message': 'Terminal not found'}), 404
    
    if action == 'start':
        # Clone repo if provided
        if repo_url:
            terminal_dir = f"terminals/{terminal_id}"
            os.makedirs(terminal_dir, exist_ok=True)
            subprocess.run(['git', 'clone', repo_url, terminal_dir], check=True)
        
        # Start the terminal process
        process = subprocess.Popen(
            ['python', '-m', 'http.server', '0'],
            cwd=f"terminals/{terminal_id}",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Update terminal status
        mongo.db.users.update_one(
            {'_id': session['user_id'], 'terminals.id': terminal_id},
            {'$set': {
                'terminals.$.status': 'running',
                'terminals.$.pid': process.pid,
                'terminals.$.repo_url': repo_url
            }}
        )
        
        active_terminals[terminal_id] = process
        return jsonify({'status': 'success', 'message': 'Terminal started'})
    
    elif action == 'stop':
        process = active_terminals.get(terminal_id)
        if process:
            process.terminate()
            del active_terminals[terminal_id]
        
        mongo.db.users.update_one(
            {'_id': session['user_id'], 'terminals.id': terminal_id},
            {'$set': {'terminals.$.status': 'stopped', 'terminals.$.pid': None}}
        )
        return jsonify({'status': 'success', 'message': 'Terminal stopped'})
    
    elif action == 'kill':
        process = active_terminals.get(terminal_id)
        if process:
            process.kill()
            del active_terminals[terminal_id]
        
        mongo.db.users.update_one(
            {'_id': session['user_id'], 'terminals.id': terminal_id},
            {'$set': {'terminals.$.status': 'killed', 'terminals.$.pid': None}}
        )
        return jsonify({'status': 'success', 'message': 'Terminal killed'})
    
    return jsonify({'status': 'error', 'message': 'Invalid action'}), 400

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('user_id', None)
    return redirect(url_for('home'))

if __name__ == '__main__':
    os.makedirs('terminals', exist_ok=True)
    app.run(debug=True)