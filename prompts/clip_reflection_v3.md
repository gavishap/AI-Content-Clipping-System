# CLIP REFLECTION V3 - Rethink With Extended Context

You previously identified a clip candidate from Nick Matau's livestream. Now you get to see EXTENDED CONTEXT — 2 minutes before and 2 minutes after the proposed clip. Your job is to RETHINK your assessment.

## THE ORIGINAL CLIP CANDIDATE

**Type**: {{CLIP_TYPE}}
**Proposed Start**: {{START_TIME}}
**Proposed End**: {{END_TIME}}
**Duration**: {{DURATION}}s
**Original Scores**: {{SCORES}}
**Money Quote**: "{{MONEY_QUOTE}}"
**Why Selected**: {{REASONING}}

## EXTENDED CONTEXT

### 2 MINUTES BEFORE THE CLIP
{{CONTEXT_BEFORE}}

### === PROPOSED CLIP START ===
{{CLIP_SEGMENT}}
### === PROPOSED CLIP END ===

### 2 MINUTES AFTER THE CLIP
{{CONTEXT_AFTER}}

## YOUR REFLECTION TASK

Now that you see the bigger picture, answer these 4 questions:

### 1. BETTER START?
Look at the 2 minutes before. Is there a stronger hook within 30 seconds of the proposed start?
- Should the clip start EARLIER to capture more setup?
- Should it start LATER because the real hook comes after the proposed start?
- Or is the current start point correct?

### 2. BETTER END?
Look at the 2 minutes after. Does Nick deliver a stronger punchline or final word nearby?
- Does the guest react MORE dramatically a few seconds after the proposed end?
- Does Nick add a killer summary line right after the proposed end?
- Is there a natural silence/pause that would be a better cut point?
- Does Nick speak last? (He should in 90% of clips)

### 3. STANDALONE CHECK
With the extended context visible:
- Does this clip ACTUALLY make sense on its own?
- Does understanding the clip require knowing what was said 2+ minutes before?
- Would a TikTok viewer be confused?

### 4. QUALITY REASSESSMENT
Now that you see the full picture:
- Is this clip STRONGER or WEAKER than it seemed in isolation?
- Is there actually a BETTER clip hiding in the extended context that was missed?
- Would you still pick this clip?

## OUTPUT FORMAT

```json
{
  "keep_clip": true,
  "adjusted_start": "[HH:MM:SS] or null if no change",
  "adjusted_end": "[HH:MM:SS] or null if no change",
  "adjustment_reasoning": "Why you changed (or didn't change) the boundaries",
  "standalone_assessment": "Does it work standalone? Explain.",
  "quality_change": "stronger | same | weaker",
  "quality_reasoning": "Why the quality assessment changed or stayed",
  "updated_scores": {
    "resolution_quality": 8,
    "hook_strength": 7,
    "standalone_clarity": 9,
    "emotional_arc": 7,
    "nick_presence": 9,
    "controversy_level": 8,
    "shareability": 7
  },
  "better_clip_nearby": "Description of a better clip if one exists in the extended context, or null",
  "pass_notes": "Any other observations from the reflection"
}
```
