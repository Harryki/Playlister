from functools import wraps
from flask import jsonify, session, redirect, request, url_for, current_app as app

def spotify_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        app.logger.debug(f"[auth] session keys: {list(session.keys())}")
        if 'spotify_token' not in session:
            if request.method == 'POST':
                app.logger.warning("[auth] Blocked POST to %s due to missing spotify_token", request.path)
                return jsonify({"error": "Authentication required"}), 401
            else:
                app.logger.info("[auth] Redirecting GET to login from %s", request.path)
                return redirect(url_for('index', next=request.url))
        return f(*args, **kwargs)
    return decorated_function