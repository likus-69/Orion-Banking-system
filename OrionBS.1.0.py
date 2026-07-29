import random
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enables JavaScript frontends to send requests to Python

# Your existing user database structure
user_data = {
    "user_1": {
        "x": 75005750990694,
        "y": "Mary Garcia",
        "balance": 1000.00
    },
    "user_2": {
        "x": 72688556523041,
        "y": "Robert Hernandez",
        "balance": 1500.00
    }
}

print("Welcome to Orion Banking Inc. Server running...")

# --- SIGN IN ENDPOINT ---
@app.route('/api/signin', methods=['POST'])
def signin():
    data = request.json
    try:
        x = int(data.get('account_number'))  # Account number
        y = str(data.get('username'))        # User name
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "Invalid input format."}), 400

    # Your original dictionary lookup logic
    for user_key, info in user_data.items():
        if info["x"] == x and info["y"].lower() == y.lower():
            return jsonify({
                "status": "success",
                "message": f"Welcome {info['y']}, Account number {info['x']}",
                "user": {
                    "username": info['y'],
                    "account_number": info['x'],
                    "balance": info.get('balance', 0.0)
                }
            }), 200

    return jsonify({"status": "error", "message": "Invalid account number or user name."}), 401


# --- SIGN UP ENDPOINT ---
@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.json
    username = data.get('username')

    if not username:
        return jsonify({"status": "error", "message": "Username is required."}), 400

    # Generate a random 14-digit account number (matching your x format)
    new_account_number = random.randint(10000000000000, 99999999999999)
    new_user_key = f"user_{len(user_data) + 1}"

    # Insert into your python dictionary
    user_data[new_user_key] = {
        "x": new_account_number,
        "y": username,
        "balance": 0.0
    }

    return jsonify({
        "status": "success",
        "message": "Account created successfully!",
        "user": {
            "username": username,
            "account_number": new_account_number,
            "balance": 0.0
        }
    }), 201


if __name__ == '__main__':
    # Run with: pip install flask flask-cors
    app.run(port=5000, debug=True)
