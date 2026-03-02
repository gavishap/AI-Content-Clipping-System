# TOPIC SEGMENTATION

You are analyzing one or more sequential chunks of a debate/discussion from Nick Matau's livestream. Segment the transcript into distinct topic blocks.

## CONVERSATION CONTEXT
Conversation: {{CONVERSATION_ID}}
Guest(s): {{GUEST_SPEAKERS}}
Time range: {{CHUNK_START}} - {{CHUNK_END}}

{{PREVIOUS_TOPICS}}

## TRANSCRIPT
{{TRANSCRIPT}}

## INSTRUCTIONS

Break the transcript into distinct topics. Analyze each chunk header separately but return ONE combined array. A topic shift occurs when:
- The subject changes (e.g., from "Israel" to "child marriage")
- A new question is asked that changes direction
- A different guest starts speaking about something new

Each topic block should be 15-60 seconds long. Very short exchanges (<10s) can be merged with an adjacent topic.

For each topic, provide:
- **topic_name**: A descriptive human-readable name (e.g., "Debate Over Gaza Genocide Definition")
- **topic_id**: A stable snake_case ID (e.g., "gaza_genocide_definition"). If the same subject was discussed earlier in this conversation or a previous chunk, REUSE the same topic_id. This is critical -- if child marriage was discussed 10 minutes ago and comes up again now, use the SAME topic_id.
- **start_time**: Timestamp in [HH:MM:SS] format
- **end_time**: Timestamp in [HH:MM:SS] format
- **key_quotes**: 1-2 short key quotes (max 30 words each)
- **speakers**: Which speakers participate in this block
- **sentiment**: One of: "heated", "calm", "confrontational", "educational", "comedic", "tense"

## OUTPUT FORMAT

Return a single flat JSON array covering ALL chunks. No extra text.

```json
[
  {
    "topic_name": "Iran Nuclear Program Discussion",
    "topic_id": "iran_nuclear",
    "start_time": "[0:34:20]",
    "end_time": "[0:35:45]",
    "key_quotes": ["do you think Netanyahu would also join a military strike?"],
    "speakers": ["nick", "deepgram_7"],
    "sentiment": "tense"
  }
]
```

## RULES
1. Every second of the transcript must be covered -- no gaps between topic blocks
2. REUSE topic_ids when the same subject recurs (across chunks or within a chunk)
3. Topic names should be specific, not vague ("Iran Nuclear Strike" not "Political Discussion")
4. Timestamps MUST come from the provided transcript
5. If a chunk is one topic, produce a single block for that chunk
6. Return one flat array for all chunks combined -- do NOT nest by chunk
