# FRAME ANALYSIS PROMPT

Analyze this video frame from a debate/podcast livestream.

## TASK

Identify the people visible and the layout of the video call/stream.

## WHAT TO IDENTIFY

1. **People Count**: How many distinct people are visible?

2. **People Descriptions**: For each person, provide:
   - Physical description (hair color/style, facial hair, glasses, age estimate)
   - Position in frame (left, right, center, top-left, top-right, etc.)
   - Whether they appear to be speaking (look for: highlighted/glowing border, mouth open, gesturing)

3. **Layout Type**: What's the panel arrangement?
   - `solo` - One person only
   - `two_panel` - Two people side by side (typical debate)
   - `multi_panel` - 3+ people in a grid layout
   - `other` - Different arrangement

4. **On-Screen Text**: Any visible:
   - Usernames or handles (@name)
   - Name labels
   - Topic/title text
   - Stream overlays

5. **Nick Identification**: If you can identify the host (Nick), note which position they're in.
   - Nick typically appears consistently in the same position throughout the stream
   - Usually the person asking questions or reacting to guests

## OUTPUT FORMAT

Return ONLY valid JSON:

```json
{
  "people_count": 2,
  "people": [
    {
      "description": "man, short dark hair, beard, mid-30s",
      "position": "left",
      "appears_speaking": true
    },
    {
      "description": "woman, blonde hair, glasses, 20s",
      "position": "right", 
      "appears_speaking": false
    }
  ],
  "layout": "two_panel",
  "on_screen_text": ["@guestname", "Topic: Israel Palestine Debate"],
  "nick_visible": true,
  "nick_position": "left"
}
```

## RULES

- If you cannot determine something with certainty, make your best estimate
- Always return valid JSON
- Position values: "left", "right", "center", "top-left", "top-right", "bottom-left", "bottom-right"
- appears_speaking should be true if the person has visual cues of active speech
