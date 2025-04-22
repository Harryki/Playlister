# project/views/analyze.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app as app
import requests

from auth import spotify_login_required
from services.youtube_scraper import scrape_music_panel_with_playwright

analyze_bp = Blueprint("analyze", __name__)

@analyze_bp.route('/analyze', methods=['GET', 'POST'])
@spotify_login_required
def analyze():
    try:
        if request.method == 'POST':
            if 'youtube_url' in request.form:
                return handle_youtube_analysis()
            else:
                return handle_playlist_creation()

        return render_template('analyze.html')
    except Exception:
        app.logger.exception("An unexpected error occurred in the /analyze route.")
        flash('An unexpected error occurred. Please try again later.', 'error')
        return redirect(url_for('index'))

def handle_youtube_analysis():
    youtube_url = request.form['youtube_url']
    metadata = scrape_music_panel_with_playwright(youtube_url)

    if not metadata:
        flash('No metadata found for the provided YouTube URL.', 'error')
        return redirect(url_for('index'))

    return render_template('analyze.html', metadata=metadata)

def handle_playlist_creation():
    app.logger.info('Create Playlist Started')
    playlist_name = request.form.get('playlist_name', 'New Playlist') or 'New Playlist'
    titles = request.form.getlist('title')
    artists = request.form.getlist('artist')
    track_uris = []

    token_info = session.get('spotify_token', {})
    access_token = token_info.get('access_token')
    if not access_token:
        flash('Spotify authentication required.', 'error')
        return redirect(url_for('login'))

    headers = {'Authorization': f'Bearer {access_token}'}
    app.logger.info('Fetch Song from Spotify started')

    for title, artist in zip(titles, artists):
        query = f'track:{title} artist:{artist}' if artist else f'track:{title}'
        response = requests.get(
            'https://api.spotify.com/v1/search',
            headers=headers,
            params={'q': query, 'type': 'track', 'limit': 1}
        )

        if response.status_code != 200:
            app.logger.error(f"Spotify search API error: {response.status_code} - {response.text}")
            continue

        tracks = response.json().get('tracks', {}).get('items', [])
        if tracks:
            track_uris.append(tracks[0]['uri'])
        else:
            app.logger.info(f"No tracks found for query: {query}")

    app.logger.info('Fetch Song from Spotify Completed')

    user_response = requests.get('https://api.spotify.com/v1/me', headers=headers)
    if user_response.status_code != 200:
        app.logger.error(f"Spotify user API error: {user_response.status_code} - {user_response.text}")
        flash('Failed to retrieve Spotify user information.', 'error')
        return redirect(url_for('index'))

    user_id = user_response.json()['id']
    playlist_response = requests.post(
        f'https://api.spotify.com/v1/users/{user_id}/playlists',
        headers=headers,
        json={'name': playlist_name, 'public': True}
    )

    if playlist_response.status_code != 201:
        app.logger.error(f"Spotify playlist creation error: {playlist_response.status_code} - {playlist_response.text}")
        flash('Failed to create Spotify playlist.', 'error')
        return redirect(url_for('index'))

    playlist_id = playlist_response.json()['id']

    if track_uris:
        add_tracks_response = requests.post(
            f'https://api.spotify.com/v1/playlists/{playlist_id}/tracks',
            headers=headers,
            json={'uris': track_uris}
        )
        if add_tracks_response.status_code != 201:
            app.logger.error(f"Spotify add tracks error: {add_tracks_response.status_code} - {add_tracks_response.text}")
            flash('Failed to add tracks to Spotify playlist.', 'error')
            return redirect(url_for('index'))

    flash('Spotify playlist created successfully!', 'success')
    app.logger.info('Create Playlist Completed')
    return redirect(url_for('index'))
