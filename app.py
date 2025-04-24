from datetime import timedelta
import sys
import time
import requests
import logging
import os

from logging.handlers import RotatingFileHandler
from flask import Flask, current_app, session, redirect, request, url_for, render_template
from flask_session import Session
import redis
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
from views.analyze import analyze_bp

load_dotenv(override=True)

redis_host = os.environ.get("REDIS_HOST", "localhost")

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)  # For session encryption
r = redis.from_url(f"redis://{redis_host}:6379")

# Redis-backed sessions
app.config.update(
    SESSION_TYPE="redis",
    SESSION_REDIS=r,
    SESSION_USE_SIGNER=True,
    SESSION_KEY_PREFIX="playlister:",
    SESSION_COOKIE_NAME="playlister_session",
    SESSION_COOKIE_SAMESITE="None",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_SECURE_COOKIE", "false").lower() == "true",
    SESSION_PERMANENT=True,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=1),
    TEMPLATES_AUTO_RELOAD=True,
)

Session(app)

formatter = logging.Formatter("[%(asctime)s] %(levelname)s in %(module)s: %(message)s")

# Stream handler for Docker logs
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
stream_handler.setLevel(logging.DEBUG)

if not app.debug and not app.testing:
    # Clear existing handlers to avoid duplicates across workers
    app.logger.handlers.clear()
    app.logger.setLevel(logging.DEBUG)
    app.logger.addHandler(stream_handler)
    app.logger.propagate = False

    # 🔥 Inherit same handlers in other modules (like scrape)
    scrape_logger = logging.getLogger("scrape")
    scrape_logger.handlers = app.logger.handlers
    scrape_logger.setLevel(app.logger.level)
    scrape_logger.propagate = False

required_vars = ["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SPOTIFY_REDIRECT_URI"]
for var in required_vars:
    if not os.getenv(var):
        raise RuntimeError(f"Missing required env var: {var}")

sp_oauth = SpotifyOAuth(
    scope="playlist-modify-public playlist-modify-private",
    redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
    client_id=os.getenv("SPOTIFY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
    cache_path=None,
    show_dialog=True
)
# ================== App Setting ==================

try:
    r.set("test", "123")
    val = r.get("test")
    app.logger.info(f"[REDIS] Test key set successfully. Value: {val}")
    app.logger.info(f"[INIT] Session backend type: {type(app.session_interface)}")
except Exception as e:
    app.logger.error(f"[REDIS] Connection or write failed: {e}")

app.register_blueprint(analyze_bp)

# @app.errorhandler(400)
# def bad_request(error):
#     return render_template('400.html', message=error.description), 400

# @app.errorhandler(404)
# def not_found_error(error):
#     app.logger.warning(f"404 error: {error}")
#     return render_template('404.html'), 404

# @app.errorhandler(500)
# def internal_error(error):
#     app.logger.error(f"500 error: {error}")
#     return render_template('500.html'), 500

def get_user_playlists(headers):
    response = requests.get('https://api.spotify.com/v1/me/playlists', headers=headers)
    if response.status_code != 200:
        app.logger.error(f"Failed to fetch playlists: {response.text}")
        return []
    return response.json().get('items', [])

@app.before_request
def log_cookie_info():
    app.logger.debug(f"[session] keys: {list(session.keys())}")
    app.logger.debug(f"[session] spotify_token: {session.get('spotify_token')}")
    app.logger.debug(f"[session] sid: {request.cookies.get('playlister_session')}")

@app.route('/')
def index():
    if 'spotify_token' in session:
        token_info = session['spotify_token']
        access_token = token_info['access_token']

        # Check if token is expired
        if token_info.get('expires_at') and time.time() > token_info['expires_at']:
            app.logger.info("[index] Spotify token expired, refreshing token.")
            try:
                token_info = sp_oauth.refresh_access_token(token_info['refresh_token'])
                session['spotify_token'] = token_info
                access_token = token_info['access_token']
                app.logger.info("[index] Spotify token refreshed successfully.")
            except Exception as e:
                app.logger.error(f"[index] Failed to refresh Spotify token: {e}")
                return redirect(url_for('index'))

        headers = {
            "Authorization": f"Bearer {access_token}"
        }

        start = time.time()
        playlists = get_user_playlists(headers)
        app.logger.info(f"[index] Spotify playlist fetch took {time.time() - start:.2f}s")

        spotify_user = session.get('spotify_user', {})
        # Log if expected keys are missing
        required_keys = ['id', 'display_name', 'images', 'followers']
        for key in required_keys:
            if key not in spotify_user:
                app.logger.warning(f"[index] Missing key '{key}' in session['spotify_user']")

        # Fallback-safe user object
        user_info = {
            'id': spotify_user.get('id', 'unknown'),
            'display_name': spotify_user.get('display_name', 'Guest'),
            'images': spotify_user.get('images', []),
            'followers': spotify_user.get('followers', {'total': 0})
        }

        return render_template('index.html', playlists=playlists, user=user_info)
    else:
        app.logger.info("[index] No Spotify token found, redirecting to login")
        auth_url = sp_oauth.get_authorize_url()
        app.logger.debug(f"[index] auth_url: {auth_url}")
        return redirect(auth_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')

    if not code:
        app.logger.warning("[CALLBACK] No authorization code received.")
        return redirect(url_for('index'))

    try:
        token_info = sp_oauth.get_access_token(code)
    except Exception as e:
        app.logger.error(f"[CALLBACK] Error getting access token: {e}")
        return redirect(url_for('index'))

    if not token_info or 'access_token' not in token_info:
        app.logger.warning("[CALLBACK] Failed to retrieve valid token_info.")
        return redirect(url_for('index'))

    # Save token and user info to session
    session['spotify_token'] = token_info
    session.permanent = True

    try:
        sp = spotipy.Spotify(auth=token_info['access_token'])
        user_info = sp.current_user()
        session['spotify_user'] = {
            'id': user_info['id'],
            'display_name': user_info['display_name'],
            'images': user_info['images'],
            'followers': user_info.get('followers', {})
        }
        app.logger.info(f"[CALLBACK] Logged in as user: {user_info['id']}")
        app.logger.debug(f"[CALLBACK] Display name: {user_info.get('display_name')}")
        app.logger.debug(f"[CALLBACK] followers : {len(user_info.get('followers', []))}")
        app.logger.debug(f"[CALLBACK] Profile image count: {len(user_info.get('images', []))}")

        # Optionally log the image URL (if present)
        if user_info.get('images'):
            app.logger.debug(f"[CALLBACK] First profile image URL: {user_info['images'][0].get('url')}")
    except Exception as e:
        app.logger.error(f"[CALLBACK] Error fetching user profile: {e}")

    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session_id = request.cookies.get(current_app.config["SESSION_COOKIE_NAME"])

    user_id = session.get('spotify_user') or 'Unknown'
    app.logger.info(f"[LOGOUT] Logging out user: {user_id}")

    token = session.get('spotify_token', {}).get('access_token')
    if token:
        app.logger.debug(f"[LOGOUT] Clearing access token: {token[:10]}...")

    session.clear()

    # Remove from Redis if session_id exists
    if session_id:
        redis_key = f"{current_app.config['SESSION_KEY_PREFIX']}{session_id}"
        r.delete(redis_key)

    app.logger.info("[LOGOUT] Session cleared.")

    return redirect("https://accounts.spotify.com/en/logout")

@app.route("/logtest")
def logtest():
    app.logger.info("📢 INFO from /logtest")
    app.logger.debug("🐛 DEBUG from /logtest")
    return "Log test route hit!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
