# Spotify Followed Artists Bulk Get

This web app retrieves a list of all artists followed by a Spotify user using the Spotify Web API.

## Features

- OAuth 2.0 authentication with Spotify
- Fetches followed artists in bulk
- Simple web interface

## Prerequisites

- Python 3.x
- A Spotify Developer account and app credentials

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/spotify-followed-artists-bulk-get.git
   cd spotify-followed-artists-bulk-get
   ```

2. Install dependencies:
   ```
   pip install flask requests
   ```

## Configuration

1. Create a Spotify app at [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
2. Note your Client ID and Client Secret.
3. Set the redirect URI in your Spotify app settings to `http://localhost:5000/callback`.
4. Update the following variables in `main.py`:
   - `CLIENT_ID`: Your Spotify app's Client ID
   - `CLIENT_SECRET`: Your Spotify app's Client Secret
   - `REDIRECT_URI`: Should match the one set in Spotify (default: `http://localhost:5000/callback`)

## Usage

1. Run the Flask app:
   ```
   python main.py
   ```

2. Open your browser and go to `http://localhost:5000`.
3. Click "Login with Spotify" to authenticate.
4. After authentication, you'll be redirected to view your followed artists.

## API Endpoints

- `/`: Home page with login link
- `/login`: Initiates Spotify OAuth flow
- `/callback`: Handles OAuth callback and token exchange
- `/followed_artists`: Displays the list of followed artists

## Limitations

- Currently displays only artist names
- Fetches up to 50 artists per request (Spotify API limit)

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License

[MIT](https://choosealicense.com/licenses/mit/)
