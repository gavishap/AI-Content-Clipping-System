# CLIP SCORING V3 - Candidate Evaluation

You are evaluating a specific clip candidate from Nick Matau's livestream. Score it on each criterion below.

## THE CANDIDATE CLIP

**Type**: {{CLIP_TYPE}}
**Pattern**: {{PATTERN}}
**Preliminary Score**: {{PRELIMINARY_SCORE}}/10

## TRANSCRIPT SEGMENT (The proposed clip)

{{TRANSCRIPT_SEGMENT}}

## SCORING CRITERIA

Rate each criterion 1-10. Be strict — Nick only posts his BEST moments.

### 1. Resolution Quality (Weight: 25%) — DEALBREAKER if < 7
How satisfying is the ending?
- 10: Guest disconnects/ragequits, or Nick delivers perfect mic-drop line
- 8-9: Nick has clear last word, guest is visibly defeated
- 6-7: Decent ending but slightly abrupt or could be stronger
- 4-5: Ending is okay but doesn't land hard
- 1-3: Clip ends mid-exchange or without clear resolution

### 2. Hook Strength (Weight: 20%) — DEALBREAKER if < 4
How quickly does the first 3-5 seconds grab attention?
- 10: Immediately shocking statement or question that demands attention
- 8-9: Strong opening that hooks within first sentence
- 6-7: Good opening but takes a moment to get going
- 4-5: Average opening, viewer might scroll past
- 1-3: Boring or confusing start

### 3. Standalone Clarity (Weight: 15%) — DEALBREAKER if < 6
Can someone with ZERO context understand and enjoy this clip?
- 10: Completely self-contained, anyone can follow
- 8-9: Very clear, minimal background needed
- 6-7: Mostly clear, one small thing might need context
- 4-5: Needs some context to fully appreciate
- 1-3: Confusing without watching the stream

### 4. Emotional Arc (Weight: 15%) — DEALBREAKER if < 3
Is there a clear emotional trajectory?
- 10: Perfect arc — calm setup → rising tension → explosive payoff
- 8-9: Strong emotional shift with clear peak
- 6-7: Decent emotional movement
- 4-5: Some emotion but flat
- 1-3: Monotone, no emotional shift

### 5. Nick Presence (Weight: 10%) — DEALBREAKER if < 5
How prominent and dominant is Nick in this clip?
- 10: Nick drives the entire exchange, delivers the key moment
- 8-9: Nick is clearly the star, controls the conversation
- 6-7: Nick is present and active
- 4-5: Nick participates but doesn't dominate
- 1-3: Nick is barely in it

### 6. Controversy Level (Weight: 10%) — DEALBREAKER if < 2
How likely is this to generate discussion/debate in comments?
- 10: Extremely polarizing, people will argue about this
- 8-9: Very controversial, strong opinions on both sides
- 6-7: Moderately controversial
- 4-5: Mildly controversial
- 1-3: Not controversial at all

### 7. Shareability (Weight: 5%) — DEALBREAKER if < 2
Would someone share this to prove a point, make someone laugh, or start a discussion?
- 10: Instantly shareable, people will tag friends
- 8-9: Very shareable moment
- 6-7: Decent share potential
- 4-5: Might share to niche audience
- 1-3: No share motivation

## MANDATORY REQUIREMENTS CHECK
Answer yes/no for each:
1. Does Nick win this interaction? (must be yes)
2. Does the guest display ignorance, hypocrisy, or anger? (must be yes)
3. Is the key moment clearly captured in the transcript? (must be yes)
4. Is this understandable without stream context? (must be yes)

## ANTI-PATTERN CHECK
Flag if ANY of these are present:
- Nick gets yelled over without getting a rebuttal in
- Amicable agreement with no tension
- Guest makes a strong point Nick can't refute
- Technical difficulties or dead air

## OUTPUT FORMAT

```json
{
  "scores": {
    "resolution_quality": 8,
    "hook_strength": 7,
    "standalone_clarity": 9,
    "emotional_arc": 7,
    "nick_presence": 9,
    "controversy_level": 8,
    "shareability": 7
  },
  "mandatory_requirements": {
    "nick_wins": true,
    "guest_displays_weakness": true,
    "key_moment_clear": true,
    "standalone": true,
    "all_passed": true
  },
  "anti_patterns_found": [],
  "emotional_arc_description": "Calm questioning -> Guest stumbles -> Nick reveals truth -> Smug satisfaction",
  "best_money_quote": "The exact best line from the clip",
  "scoring_notes": "Brief explanation of scores"
}
```
