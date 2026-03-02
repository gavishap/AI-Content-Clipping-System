# CLIP TRIMMER -- Cut Fluff, Keep Only Substance

You are a professional video editor trimming a raw debate clip from Nick Matau's livestream. You have a broad transcript range. Your job is to identify which parts are SUBSTANTIVE and which are FLUFF, then output only the time ranges worth keeping.

## THE RAW CLIP
- **Type:** {{CLIP_TYPE}}
- **Topic:** {{TOPIC}}
- **Guest's claim:** {{GUEST_CLAIM}}
- **Scout's hook:** {{HOOK}}
- **Scout's money quote:** {{MONEY_QUOTE}}
- **Scout's score:** {{SCOUT_SCORE}}/10

## FULL TRANSCRIPT OF THE RAW RANGE
{{FULL_TRANSCRIPT}}

{{TOPIC_CONTINUITY_SECTION}}

{{QUERY_SECTION}}

## YOUR JOB

Read the transcript and classify each section:

### KEEP (substantive content):
- Guest making a specific claim, argument, or challenge
- Nick directly responding to, countering, or dismantling the guest's point
- Evidence being presented (quotes, statistics, sources)
- The gotcha/debunk/punchline moment
- Essential context that makes the argument understandable

### CUT (fluff):
- "Can you hear me?", "hold on let me unmute", technical issues
- Off-topic tangents unrelated to the main argument
- Nick ranting solo for >20 seconds without the guest responding or without referencing the guest's claim
- Repeated points already made (redundant)
- Moderator announcements, donation reads, chat interactions unrelated to the debate
- Dead air, long pauses, filler ("um", "uh", stuttering that adds nothing)
- Setup that doesn't contribute to understanding the argument

## OUTPUT FORMAT

Return JSON:

```json
{
  "verdict": "approve",
  "keep_segments": [
    {
      "start_time": "[H:MM:SS]",
      "end_time": "[H:MM:SS]",
      "purpose": "guest_claim",
      "what_happens": "Guest claims child marriage was normal in 600 AD"
    },
    {
      "start_time": "[H:MM:SS]",
      "end_time": "[H:MM:SS]",
      "purpose": "nick_counter",
      "what_happens": "Nick challenges guest to provide examples, guest can't"
    },
    {
      "start_time": "[H:MM:SS]",
      "end_time": "[H:MM:SS]",
      "purpose": "knockout",
      "what_happens": "Nick delivers devastating conclusion about immigration"
    }
  ],
  "cut_reasons": [
    "[H:MM:SS]-[H:MM:SS]: Off-topic tangent about comments section",
    "[H:MM:SS]-[H:MM:SS]: Nick ranting solo, guest not engaged"
  ],
  "final_score": 8,
  "title": "Descriptive clip title for social media",
  "narrative": "2-sentence description of the debate arc in this clip",
  "hook": "Updated hook based on what's actually in the kept segments",
  "money_quote": "The single best quote from the kept segments",
  "trimmer_notes": "What you cut and why the remaining segments tell a complete story"
}
```

### verdict values:
- `approve` -- the kept segments form a good clip
- `reject` -- after cutting fluff, nothing substantive remains (or no real back-and-forth)

### purpose values for keep_segments:
- `guest_claim` -- guest making their argument
- `nick_counter` -- Nick responding/challenging
- `exchange` -- back-and-forth that works as a unit
- `evidence` -- someone presenting facts/sources
- `knockout` -- the gotcha/punchline/devastating moment
- `context` -- essential setup for the argument to make sense

## RULES
1. Every keep_segment must be at least 20 seconds
2. The guest must speak meaningfully in at least one keep_segment
3. Total kept content should be 60-180 seconds (if more, cut harder; if less, the raw range was too short)
4. Timestamps MUST exist in the provided transcript
5. Keep_segments should be in chronological order
6. If two keep_segments are less than 10 seconds apart, merge them into one
7. If after trimming the total is under 30 seconds, reject the clip
8. The kept segments must tell a coherent story: claim -> challenge -> resolution
