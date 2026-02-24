# Hacker News Daily Digest

A Python script that generates a daily PDF of the top 10 Hacker News posts from the previous day. Each PDF includes a table of contents, the full article content (when available), and the top 5 most engaged-with comments per post.

## Features

- Fetches yesterday's top 10 HN posts via the Algolia API
- Extracts article content from linked URLs using readability-lxml
- Includes the top 5 comments per post from the Firebase HN API
- Generates a styled PDF with a clickable table of contents
- Runs daily on macOS via launchd

## Requirements

- Python 3.10+
- macOS (for launchd scheduling; the script itself runs anywhere)
- Homebrew (for system dependencies)

## Setup

### 1. Install system dependencies

```bash
brew install cairo pango gdk-pixbuf libffi
```

### 2. Create a virtual environment and install Python dependencies

```bash
cd /path/to/hn-daily-digest
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Run manually

```bash
.venv/bin/python3 hn_digest.py
```

The PDF will be saved to `~/Documents/hn-digests/YYYY-MM-DD.pdf`.

### 4. Schedule daily runs (macOS)

Copy the example plist and replace `YOUR_USERNAME` with your macOS username:

```bash
cp com.user.hn-digest.plist.example com.user.hn-digest.plist
```

Edit `com.user.hn-digest.plist` and replace every instance of `YOUR_USERNAME` with your actual macOS username. You should also update the paths if you cloned this repo to a different location.

Then install and load the agent:

```bash
cp com.user.hn-digest.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.user.hn-digest.plist
```

The script will run daily at 7:00 AM. To change the time, edit the `Hour` and `Minute` values in the plist.

To verify it's loaded:

```bash
launchctl list | grep hn-digest
```

To unload:

```bash
launchctl unload ~/Library/LaunchAgents/com.user.hn-digest.plist
```

## Output

PDFs are saved to `~/Documents/hn-digests/` with the format `YYYY-MM-DD.pdf`. Logs are written to the same directory.
