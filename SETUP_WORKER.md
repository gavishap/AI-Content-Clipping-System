# Worker Setup Guide

## 1. Google Cloud Setup (one-time, ~10 minutes)

### Create Project & Enable APIs
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (e.g., "Nick Matau Clipper")
3. Enable these APIs:
   - **Google Sheets API** — [Enable](https://console.cloud.google.com/apis/library/sheets.googleapis.com)
   - **Google Drive API** — [Enable](https://console.cloud.google.com/apis/library/drive.googleapis.com)

### Create Service Account
1. Go to **IAM & Admin → Service Accounts**
2. Click **Create Service Account**
3. Name: `clipper-worker`
4. Click **Create and Continue** (skip optional permissions)
5. Click **Done**
6. Click on the new service account → **Keys** tab → **Add Key → Create New Key → JSON**
7. Download the JSON file — this is your `credentials.json`
8. Note the service account email (looks like `clipper-worker@project-id.iam.gserviceaccount.com`)

## 2. Google Sheet Setup

### Create the Sheet
1. Create a new Google Sheet
2. Name it: "Nick Matau Clip Jobs"
3. Set the **header row** (Row 1) to:
   ```
   Timestamp | Video URL | Query | Max Clips | Status | Report Link | Clips Folder | Error
   ```
4. Share the sheet with the service account email (Editor access)
5. Copy the Sheet ID from the URL: `https://docs.google.com/spreadsheets/d/{THIS_IS_THE_ID}/edit`

### Create the Google Form (optional, for Nick)
1. Create a Google Form linked to this Sheet
2. Add fields:
   - "Video URL" (Short answer, required)
   - "Query" (Short answer, optional)
   - "Max Clips" (Dropdown: 5, 10, 15, 20)
3. Link responses to the Sheet above
4. Share the form link with Nick

## 3. Google Drive Setup

1. In Google Drive, create a folder: "Nick Matau Clips"
2. Share it with the service account email (Editor access)
3. Copy the folder ID from the URL: `https://drive.google.com/drive/folders/{THIS_IS_THE_ID}`

## 4. Railway Deployment

### Connect & Deploy
1. Go to [Railway](https://railway.app/) and create a new project
2. Connect your GitHub repo (or deploy from local with `railway up`)
3. The Dockerfile will be auto-detected

### Set Environment Variables
In Railway dashboard → Variables, add:

```
DEEPGRAM_API_KEY=your_deepgram_key
ANTHROPIC_API_KEY=your_anthropic_key
PYANNOTE_API_KEY=your_pyannote_key
GOOGLE_SHEET_ID=your_sheet_id
GOOGLE_DRIVE_FOLDER_ID=your_drive_folder_id
GOOGLE_CREDENTIALS_JSON=<base64 encoded credentials.json>
POLL_INTERVAL=120
VOICEPRINT_PATH=/app/nick_voiceprint.json
```

To base64-encode your credentials:
```bash
# PowerShell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("path/to/credentials.json"))

# Linux/Mac
base64 -w 0 credentials.json
```

### Verify
1. Add a test row to the Google Sheet:
   - Video URL: `https://www.youtube.com/watch?v=dQw4w9WgXcQ`
   - Query: (leave blank)
   - Max Clips: 5
2. Watch Railway logs — worker should pick it up within 2 minutes
3. Status should change to "processing" then "complete"
4. Clips Folder column should have a Google Drive link

## 5. How Nick Uses It

1. Open the Google Form (bookmarked link)
2. Paste the YouTube stream URL
3. Optionally add a query like "child marriage in islam"
4. Set max clips (default 10)
5. Submit
6. Wait ~20-30 minutes
7. Check the Google Sheet — when Status = "complete", click the "Clips Folder" link
8. Find all MP4 clips + the full report in Google Drive
