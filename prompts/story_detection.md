# STORY CONNECTION DETECTION

You are analyzing a conversation from Nick Matau's debate livestream to find thematic connections that can be stitched into composite video clips.

## WHO IS NICK
Nick debates guests on religion, politics, and philosophy. His best clips show contradictions, gotcha moments, and emotional escalations. He uses Socratic questioning and fact-checking.

## THE CONVERSATION
Guest(s): {{GUEST_SPEAKERS}}
Duration: {{DURATION}}
Topics found: {{TOPICS_JSON}}

## TRANSCRIPT
{{TRANSCRIPT}}

{{QUERY_SECTION}}

## WHAT TO FIND

Look for connections between moments that are NOT next to each other in the conversation. These non-contiguous segments, when played back-to-back, create a compelling story.

### Connection Types

1. **CONTRADICTION**: Guest says X at one point, then says not-X later.
   - Example: "I've never supported violence" at 5:00, then "sometimes violence is necessary" at 18:00

2. **GOTCHA_ARC**: Nick sets up a question/trap early, guest walks into it later.
   - Example: Nick asks about a definition at 2:00, guest gives a wrong answer at 15:00, Nick reveals truth at 16:00

3. **ESCALATION**: Guest starts calm and reasonable, then progressively loses composure.
   - Example: Polite tone at 3:00, raised voice at 12:00, yelling/insults at 20:00

4. **HYPOCRISY**: Guest applies different standards to different groups/situations.
   - Example: "Everyone deserves rights" at 4:00, then "except for [group]" at 22:00

5. **KNOWLEDGE_COLLAPSE**: Guest claims expertise, then reveals fundamental ignorance.
   - Example: "I've studied this for years" at 1:00, can't answer basic question at 10:00

## OUTPUT FORMAT

Return a JSON array of story proposals. Each proposal has 2-5 non-contiguous segments:

```json
[
  {
    "story_type": "contradiction",
    "title": "Short descriptive title",
    "narrative": "2-3 sentences explaining the story arc and why it's compelling",
    "segments": [
      {
        "start_time": "[HH:MM:SS]",
        "end_time": "[HH:MM:SS]",
        "purpose": "setup",
        "transcript_excerpt": "Key quote from this segment",
        "matches_target": null
      },
      {
        "start_time": "[HH:MM:SS]",
        "end_time": "[HH:MM:SS]",
        "purpose": "contradiction",
        "transcript_excerpt": "Contradicting quote",
        "matches_target": null
      }
    ],
    "score": 8,
    "reasoning": "Why these segments work together as a video"
  }
]
```

## RULES
1. Segments must be from DIFFERENT parts of the conversation (not adjacent)
2. Each segment should be 15-90 seconds (enough context to understand)
3. Total story duration should be 45-300 seconds
4. Timestamps MUST exist in the provided transcript
5. Include 2-5 proposals per conversation (quality over quantity)
6. Return empty array `[]` if no good connections exist
7. score is 1-10 (only include if >= 6)
8. The "purpose" field must be one of: "setup", "contradiction", "reaction", "payoff", "escalation", "evidence"
