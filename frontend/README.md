# Nick Matau Clipper Frontend

Modern dashboard for visualizing and editing AI-extracted clips from Nick Matau's livestreams.

## Setup

1.  **Install dependencies:**
    ```bash
    npm install
    ```

2.  **Run the development server:**
    ```bash
    npm run dev
    ```

3.  Open [http://localhost:3000](http://localhost:3000) with your browser.

## Features

-   **Timeline Visualization:** Interactive SVG timeline showing conversations, topics, and clip suggestions.
-   **Video Player:** Synced video playback with the timeline. (Currently using a placeholder YouTube video).
-   **Clip Editor:** Review suggested clips, adjust segment boundaries, and preview composite clips (stitched segments).
-   **Modern UI:** Built with Next.js 14, Tailwind CSS, and Shadcn UI.

## Data Source

The app loads static JSON data from `src/data/`:
-   `conversation_map.json`: Conversation segments.
-   `topic_map.json`: Detailed topic blocks.
-   `unified_clips_results.json`: AI-suggested clips.

To update the data, run the backend pipeline:
```bash
python main.py find-clips-unified ...
```
Then copy the outputs to `frontend/src/data/`.

## Configuration

To change the video source, edit `src/components/player/VideoPlayer.tsx` and update `VIDEO_URL`.
