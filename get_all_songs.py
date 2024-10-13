"""
@file get_all_songs.py
@brief This file contains the code to get all songs from the Spotify API. 
		- list all the playlists that the user has liked, saved, downloaded, or added to their library.
    - confirm that the user is okay with the list
    - download the names and all the metadata of these songs (not the audio)
    - save all this in one json file that contains all the playlists
    - the hierarchy should be playlist_name -> song_name -> song_metadata
    - song metadata should include everything that spotify knows about that song including user streaming history
    - each part of the code should be neatly organized into functions so that parts of it can be used 
      later for other projects. Especially the parts where we use the spotify API.
"""

# Add this comment to do nothing
# This is a test comment

import os
import json
from typing import List, Dict, Tuple
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import CacheFileHandler
from datetime import datetime
import signal
import sys
import logging
from functools import lru_cache
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def signal_handler(sig, frame):
    print('\nCtrl+C detected. Exiting gracefully...')
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def get_spotify_client() -> spotipy.Spotify:
    """
    Create and return an authenticated Spotify client.

    This function reads Spotify API credentials from environment variables
    and sets up the necessary authentication scope. It uses a cache file to
    store and retrieve the access token, minimizing the need for manual authentication.

    @return: An authenticated Spotify client object.
    @rtype: spotipy.Spotify
    """
    client_id = os.getenv('SPOTIPY_CLIENT_ID')
    client_secret = os.getenv('SPOTIPY_CLIENT_SECRET')
    redirect_uri = os.getenv('SPOTIPY_REDIRECT_URI')

    if not all([client_id, client_secret, redirect_uri]):
        print("Error: Missing Spotify API credentials. Please check your .env file.")
        sys.exit(1)

    scope = "playlist-read-private playlist-read-collaborative user-library-read"
    cache_handler = CacheFileHandler(cache_path=".spotifycache")
    auth_manager = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=scope,
        cache_handler=cache_handler,
        open_browser=False
    )
    
    # Check if there's a valid token in the cache
    if not auth_manager.validate_token(cache_handler.get_cached_token()):
        # If no valid token, we need to get a new one
        print("No valid token found. Please authenticate manually.")
        auth_url = auth_manager.get_authorize_url()
        print(f"\nPlease navigate to the following URL to authorize the application:")
        print(auth_url)
        print("\nAfter authorizing, you will be redirected to a URL. Please copy and paste that URL here:")
        response = input("Enter the URL you were redirected to: ").strip()
        
        # Extract the code from the response URL
        code = auth_manager.parse_response_code(response)
        
        # Get and cache the access token
        auth_manager.get_access_token(code)
    
    return spotipy.Spotify(auth_manager=auth_manager)

def get_user_playlists_and_saved_tracks(sp: spotipy.Spotify) -> Tuple[List[Dict], List[Dict]]:
    """
    Retrieve all playlists that the user has liked, saved, or added to their library,
    as well as the user's saved tracks.

    @param sp: An authenticated Spotify client object. (inparam)
    @type sp: spotipy.Spotify
    @return: A tuple containing a list of playlists and a list of saved tracks.
    @rtype: Tuple[List[Dict], List[Dict]]
    """
    playlists = []
    results = sp.current_user_playlists()
    while results:
        for playlist in results['items']:
            if playlist['tracks']['total'] > 0:
                playlists.append(playlist)
        if results['next']:
            results = sp.next(results)
        else:
            break
    
    # Get saved tracks
    saved_tracks = get_saved_tracks(sp)
    
    # Add "Liked Songs" as a playlist if there are saved tracks
    if saved_tracks:
        liked_songs_playlist = {
            'id': 'liked_songs',
            'name': 'Liked Songs',
            'tracks': {'total': len(saved_tracks)}
        }
        playlists.append(liked_songs_playlist)
    
    # Sort playlists alphabetically by name
    playlists.sort(key=lambda x: x['name'].lower())
    
    return playlists, saved_tracks

def get_saved_tracks(sp: spotipy.Spotify) -> List[Dict]:
    """
    Retrieve all saved tracks from the user's library.

    @param sp: An authenticated Spotify client object. (inparam)
    @type sp: spotipy.Spotify
    @return: A list of dictionaries, where each dictionary contains information about a saved track.
    @rtype: List[Dict]
    """
    tracks = []
    results = sp.current_user_saved_tracks()
    while results:
        tracks.extend(results['items'])
        if results['next']:
            results = sp.next(results)
        else:
            break
    return tracks

@lru_cache(maxsize=None)
def get_playlist_tracks(sp: spotipy.Spotify, playlist_id: str) -> List[Dict]:
    """
    Retrieve all tracks from a given playlist.

    @param sp: An authenticated Spotify client object. (inparam)
    @type sp: spotipy.Spotify
    @param playlist_id: The Spotify ID of the playlist. (inparam)
    @type playlist_id: str
    @return: A list of dictionaries, where each dictionary contains information about a track.
    @rtype: List[Dict]
    """
    if playlist_id == 'liked_songs':
        return get_saved_tracks(sp)
    
    tracks = []
    results = sp.playlist_tracks(playlist_id)
    while results:
        tracks.extend(results['items'])
        if results['next']:
            results = sp.next(results)
        else:
            break
    return tracks

def format_track_data(track: Dict) -> Dict:
    """
    Format track data for export.

    @param track: Raw track data from Spotify API.
    @type track: Dict
    @return: Formatted track data.
    @rtype: Dict
    """
    if not isinstance(track, dict) or 'track' not in track:
        logging.error(f"Invalid track data: {track}")
        return {}

    track_info = track['track']

    return {
        'id': track_info.get('id', ''),
        'name': track_info.get('name', ''),
        'artists': [artist.get('name', '') for artist in track_info.get('artists', [])],
        'album': track_info.get('album', {}).get('name', ''),
        'duration_ms': track_info.get('duration_ms', 0),
        'added_at': track.get('added_at', ''),
        'uri': track_info.get('uri', ''),
        'external_url': track_info.get('external_urls', {}).get('spotify', '')
    }

def save_playlists_to_json(playlists_data: Dict[str, Dict[str, Dict]]):
    """
    Save the playlists data to JSON files in a timestamped output directory.

    @param playlists_data: A nested dictionary containing all playlist and track data. (inparam)
    @type playlists_data: Dict[str, Dict[str, Dict]]
    """
    timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    output_dir = os.path.join(os.path.dirname(__file__), 'output', f'spotify_export_{timestamp}')
    os.makedirs(output_dir, exist_ok=True)

    # Full data export
    full_export_data = {
        'export_date': datetime.now().isoformat(),
        'playlists': []
    }

    # Minimal data export
    minimal_export_data = {
        'export_date': datetime.now().isoformat(),
        'playlists': []
    }

    for playlist_name, playlist_data in playlists_data.items():
        logging.info(f"Processing playlist: {playlist_name}")
        
        if playlist_data is None:
            logging.warning(f"Playlist data is None for {playlist_name}")
            continue
        
        playlist_info = playlist_data.get('playlist_info')
        if playlist_info is None:
            logging.warning(f"Playlist info is None for {playlist_name}")
            continue
        
        # Full data formatting
        full_playlist = {
            'id': playlist_info.get('id'),
            'name': playlist_info.get('name'),
            'description': playlist_info.get('description', ''),
            'owner': playlist_info.get('owner', {}).get('display_name', 'You'),
            'tracks_count': playlist_info.get('tracks', {}).get('total', 0),
            'tracks': []
        }
        
        # Minimal data formatting
        minimal_playlist = {
            'name': playlist_info.get('name'),
            'tracks': []
        }
        
        tracks = playlist_data.get('tracks', [])
        if tracks is None:
            logging.warning(f"Tracks is None for {playlist_name}")
            tracks = []
        
        for track in tracks:
            if track is None:
                logging.warning(f"Found a None track in {playlist_name}")
                continue
            try:
                full_track = format_track_data(track)
                full_playlist['tracks'].append(full_track)
                
                # Minimal track data
                artists_str = ', '.join(full_track['artists'])
                minimal_track = f"{full_track['name']} - [{artists_str}]"
                minimal_playlist['tracks'].append(minimal_track)
            except Exception as e:
                logging.error(f"Error formatting track in {playlist_name}: {str(e)}")
                logging.error(f"Problematic track data: {track}")
        
        full_export_data['playlists'].append(full_playlist)
        minimal_export_data['playlists'].append(minimal_playlist)

    # Save full data
    full_filepath = os.path.join(output_dir, 'full_export.json')
    with open(full_filepath, 'w', encoding='utf-8') as f:
        json.dump(full_export_data, f, indent=2, ensure_ascii=False)

    # Save minimal data
    minimal_filepath = os.path.join(output_dir, 'minimal_export.json')
    with open(minimal_filepath, 'w', encoding='utf-8') as f:
        json.dump(minimal_export_data, f, indent=2, ensure_ascii=False)

    logging.info(f"Full playlist data has been exported to '{full_filepath}'")
    logging.info(f"Minimal playlist data has been exported to '{minimal_filepath}'")
    print(f"Playlist data has been exported to the directory: '{output_dir}'")

def confirm_playlists(playlists: List[Dict]) -> bool:
    """
    Display the list of playlists to the user and ask for confirmation.

    @param playlists: A list of playlist dictionaries. (inparam)
    @type playlists: List[Dict]
    @return: True if the user confirms, False otherwise.
    @rtype: bool
    """
    print("\nThe following playlists were found:")
    for i, playlist in enumerate(playlists, 1):
        print(f"{i}. {playlist['name']} ({playlist['tracks']['total']} tracks)")
    
    while True:
        response = input("\nAre you okay with this list? (y/n): ").lower().strip()
        if response in ['y', 'yes']:
            return True
        elif response in ['n', 'no']:
            return False
        else:
            print("Please enter 'y' for yes or 'n' for no.")

def main():
    try:
        print("Starting Spotify authentication process...")
        sp = get_spotify_client()
        
        print("Authentication successful. Fetching user playlists and saved tracks...")
        playlists, saved_tracks = get_user_playlists_and_saved_tracks(sp)
        
        if not confirm_playlists(playlists):
            print("Operation cancelled by user. Exiting...")
            sys.exit(0)
        
        all_playlist_data = {}
        for playlist in playlists:
            print(f"Fetching tracks for playlist: {playlist['name']}")
            tracks = get_playlist_tracks(sp, playlist['id'])
            all_playlist_data[playlist['name']] = {
                'playlist_info': playlist,
                'tracks': tracks
            }
        
        print("Exporting all playlist data to JSON...")
        save_playlists_to_json(all_playlist_data)
        
        print("Export completed successfully!")
    except KeyboardInterrupt:
        print("\nOperation cancelled by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
