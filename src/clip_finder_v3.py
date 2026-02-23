"""
Clip Finder V3 - Data-Driven Clip Detection with Reflection & Debate

Owner: Gabriel
Status: Implemented
Version: 3.0

5-pass pipeline for finding viral-worthy clips from Nick Matau's livestreams:
  1. DETECT  - Find raw candidates in transcript windows (Claude)
  2. SCORE   - Rate each candidate on weighted rubric (Claude + programmatic)
  3. FILTER  - Kill mandatory-fail candidates (programmatic)
  4. REFLECT - Rethink with extended context, adjust boundaries (Claude)
  5. DEBATE  - Challenge borderline clips via Multi-Agent Debate (Claude)

Uses existing infrastructure:
  - src/anthropic_client.py (ClaudeClient with retry, JSON, costs)
  - src/llm_engineering.py (MultiAgentDebate, SelfConsistencyRunner)

Input: Enhanced utterance transcript (episode_XXX_transcript_v3.json)
Output: Ranked clips with per-pass explanations
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.anthropic_client import ClaudeClient, CostTracker
from src.llm_engineering import MultiAgentDebate, DebateVerdict

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class DurationConfig:
    """Duration constraints from the Nick Clip Profile."""
    min_seconds: int
    max_seconds: int
    sweet_spot_min: int
    sweet_spot_max: int
    average: int
    median: int


@dataclass
class ScoringWeight:
    """A single scoring criterion with weight and threshold."""
    weight: int
    dealbreaker_threshold: int


@dataclass
class NickClipProfile:
    """Loaded from nick_clip_profile.json - the scoring brain."""
    duration: DurationConfig
    scoring_weights: Dict[str, ScoringWeight]
    hook_types_ranked: List[str]
    clip_types_ranked: List[str]
    topics_ranked: List[str]
    mandatory_requirements: List[str]
    anti_patterns: List[str]
    nick_speaks_last_pct: int
    avg_turn_count: int
    nick_talk_time_ratio: float

    @classmethod
    def load(cls, path: str) -> "NickClipProfile":
        """Load profile from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        p = raw["nick_clip_profile"]
        dur = p["duration"]
        sw = {
            k: ScoringWeight(weight=v["weight"], dealbreaker_threshold=v["dealbreaker_threshold"])
            for k, v in p["scoring_weights"].items()
        }
        sd = p["speaker_dynamics"]
        return cls(
            duration=DurationConfig(**dur),
            scoring_weights=sw,
            hook_types_ranked=p["hook_types_ranked"],
            clip_types_ranked=p["clip_types_ranked"],
            topics_ranked=p["topics_ranked"],
            mandatory_requirements=p["mandatory_requirements"],
            anti_patterns=p["anti_patterns"],
            nick_speaks_last_pct=sd["nick_speaks_last_pct"],
            avg_turn_count=sd["avg_turn_count"],
            nick_talk_time_ratio=sd["nick_talk_time_ratio"],
        )


@dataclass
class Utterance:
    """A single speaker turn from the enhanced transcript."""
    speaker: str
    start: float
    end: float
    text: str
    word_count: int


@dataclass
class TranscriptWindow:
    """A segment of utterances for analysis."""
    window_id: int
    utterances: List[Utterance]
    start_time: float
    end_time: float
    formatted_text: str


@dataclass
class PassInfo:
    """Explanation of what happened in a specific pipeline pass."""
    pass_name: str
    result: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ClipCandidate:
    """A clip candidate with scores and per-pass explanations."""
    clip_id: str
    start_time: float
    end_time: float
    duration: float
    clip_type: str
    pattern: str
    hook: str
    money_quote: str
    peak_moment: str
    nick_role: str

    # Scores (populated in scoring pass)
    scores: Dict[str, float] = field(default_factory=dict)
    composite_score: float = 0.0

    # Programmatic metrics
    nick_speaks_last: bool = False
    turn_count: int = 0
    nick_talk_ratio: float = 0.0

    # Metadata
    emotional_arc: str = ""
    transcript_excerpt: str = ""
    reasoning: str = ""
    confidence: float = 0.0

    # Per-pass trail (the explanations the user wants)
    pass_trail: List[PassInfo] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON output."""
        d = asdict(self)
        d["pass_trail"] = [asdict(p) for p in self.pass_trail]
        return d


# =============================================================================
# Prompt Loader
# =============================================================================

def _load_prompt(name: str) -> str:
    """Load a prompt template from prompts/ directory."""
    prompt_dir = Path(__file__).parent.parent / "prompts"
    path = prompt_dir / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")


# =============================================================================
# Utility: Format Utterances
# =============================================================================

def _format_time(seconds: float) -> str:
    """Convert seconds to [H:MM:SS] format."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"[{h}:{m:02d}:{s:02d}]"


def _format_utterances(utterances: List[Utterance]) -> str:
    """Format utterances as readable transcript text."""
    lines = []
    for u in utterances:
        lines.append(f"{_format_time(u.start)} {u.speaker}: {u.text}")
    return "\n".join(lines)


def _parse_timestamp(ts: str) -> Optional[float]:
    """Parse [H:MM:SS] or [HH:MM:SS] timestamp to seconds."""
    ts = ts.strip().strip("[]")
    parts = ts.split(":")
    try:
        if len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            return h * 3600 + m * 60 + s
        elif len(parts) == 2:
            m, s = int(parts[0]), int(parts[1])
            return m * 60 + s
    except (ValueError, IndexError):
        pass
    return None


# =============================================================================
# Main Class
# =============================================================================

class ClipFinderV3:
    """
    Data-driven clip finder using Nick Clip Profile + 5-pass pipeline.

    Usage:
        finder = ClipFinderV3()
        clips = await finder.find_clips("outputs/episode_258_transcript_v3.json")
    """

    WINDOW_SECONDS = 300       # 5-minute analysis windows
    OVERLAP_SECONDS = 120      # 2-minute overlap between windows
    BORDERLINE_LOW = 45        # Score below this = reject
    BORDERLINE_HIGH = 65       # Score above this = auto-pass
    CONTEXT_SECONDS = 120      # 2 minutes of context for reflection

    def __init__(
        self,
        profile_path: Optional[str] = None,
        client: Optional[ClaudeClient] = None,
    ):
        """
        Initialize the clip finder.

        Args:
            profile_path: Path to nick_clip_profile.json (defaults to project root)
            client: Optional pre-configured ClaudeClient
        """
        if profile_path is None:
            profile_path = str(Path(__file__).parent.parent / "nick_clip_profile.json")
        self.profile = NickClipProfile.load(profile_path)

        self.client = client or ClaudeClient()
        self.debate = MultiAgentDebate(self.client)

        # Load prompt templates
        self._detection_prompt = _load_prompt("clip_detection_v3.md")
        self._scoring_prompt = _load_prompt("clip_scoring_v3.md")
        self._reflection_prompt = _load_prompt("clip_reflection_v3.md")

        logger.info("ClipFinderV3 initialized")

    # =========================================================================
    # STEP 0: Load Transcript
    # =========================================================================

    def _load_transcript(self, path: str) -> List[Utterance]:
        """Load enhanced transcript from JSON or parse from .txt."""
        path = str(path)
        if path.endswith(".json"):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [
                Utterance(
                    speaker=u["speaker"],
                    start=u["start"],
                    end=u["end"],
                    text=u["text"],
                    word_count=u.get("word_count", len(u["text"].split())),
                )
                for u in data["utterances"]
            ]
        elif path.endswith(".txt"):
            return self._parse_txt_transcript(path)
        else:
            raise ValueError(f"Unsupported transcript format: {path}")

    def _parse_txt_transcript(self, path: str) -> List[Utterance]:
        """Parse [H:MM:SS] speaker: text format."""
        utterances = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # Parse [H:MM:SS] speaker: text
                if line.startswith("["):
                    bracket_end = line.index("]")
                    ts_str = line[1:bracket_end]
                    rest = line[bracket_end + 2:]  # skip "] "
                    colon_idx = rest.index(":")
                    speaker = rest[:colon_idx].strip()
                    text = rest[colon_idx + 1:].strip()
                    seconds = _parse_timestamp(ts_str)
                    if seconds is not None:
                        utterances.append(Utterance(
                            speaker=speaker,
                            start=seconds,
                            end=seconds + len(text.split()) * 0.3,  # estimate
                            text=text,
                            word_count=len(text.split()),
                        ))
        return utterances

    # =========================================================================
    # STEP 1: Segment Transcript into Windows
    # =========================================================================

    def _segment_transcript(self, utterances: List[Utterance]) -> List[TranscriptWindow]:
        """Break utterances into overlapping time-based windows."""
        if not utterances:
            return []

        total_start = utterances[0].start
        total_end = utterances[-1].end
        windows = []
        window_id = 0
        current_start = total_start

        while current_start < total_end:
            window_end = current_start + self.WINDOW_SECONDS
            # Gather utterances in this time range
            window_utts = [
                u for u in utterances
                if u.start >= current_start and u.start < window_end
            ]
            if window_utts:
                windows.append(TranscriptWindow(
                    window_id=window_id,
                    utterances=window_utts,
                    start_time=current_start,
                    end_time=min(window_end, total_end),
                    formatted_text=_format_utterances(window_utts),
                ))
                window_id += 1

            current_start += self.WINDOW_SECONDS - self.OVERLAP_SECONDS

        logger.info(f"Segmented transcript into {len(windows)} windows")
        return windows

    # =========================================================================
    # STEP 2: Detect Candidates (Claude)
    # =========================================================================

    async def _detect_candidates(self, window: TranscriptWindow) -> List[ClipCandidate]:
        """Send a window to Claude and get raw clip candidates."""
        prompt = self._detection_prompt.replace("{{TRANSCRIPT}}", window.formatted_text)

        try:
            response = await self.client.complete_json(
                prompt=prompt,
                max_tokens=4096,
                temperature=0.1,
            )
            data = response.extract_json()
        except Exception as e:
            logger.warning(f"Detection failed for window {window.window_id}: {e}")
            return []

        if data is None:
            return []

        # Handle both list and dict-with-list responses
        candidates_raw = data if isinstance(data, list) else data.get("candidates", data.get("clips", []))
        if not isinstance(candidates_raw, list):
            return []

        candidates = []
        for i, raw in enumerate(candidates_raw):
            start_ts = _parse_timestamp(raw.get("start_time", ""))
            end_ts = _parse_timestamp(raw.get("end_time", ""))
            if start_ts is None or end_ts is None:
                continue

            duration = end_ts - start_ts
            if duration < self.profile.duration.min_seconds:
                continue

            cand = ClipCandidate(
                clip_id=f"w{window.window_id}_c{i}",
                start_time=start_ts,
                end_time=end_ts,
                duration=duration,
                clip_type=raw.get("clip_type", "UNKNOWN"),
                pattern=raw.get("pattern", "unknown"),
                hook=raw.get("hook", ""),
                money_quote=raw.get("money_quote", ""),
                peak_moment=raw.get("peak_moment", ""),
                nick_role=raw.get("nick_role", "questioner"),
                reasoning=raw.get("why_this_is_a_clip", ""),
            )
            cand.pass_trail.append(PassInfo(
                pass_name="1_DETECTION",
                result="FOUND",
                details={
                    "window_id": window.window_id,
                    "window_time": f"{_format_time(window.start_time)} - {_format_time(window.end_time)}",
                    "preliminary_score": raw.get("preliminary_score", 0),
                    "clip_type": cand.clip_type,
                    "pattern": cand.pattern,
                    "why": cand.reasoning,
                },
            ))
            candidates.append(cand)

        logger.info(
            f"Window {window.window_id} ({_format_time(window.start_time)}): "
            f"{len(candidates)} candidates"
        )
        return candidates

    # =========================================================================
    # STEP 3: Score Candidates (Hybrid: Claude + Programmatic)
    # =========================================================================

    def _compute_programmatic_scores(
        self, candidate: ClipCandidate, utterances: List[Utterance]
    ) -> None:
        """Compute measurable metrics without LLM."""
        segment = [
            u for u in utterances
            if u.start >= candidate.start_time and u.end <= candidate.end_time + 2
        ]
        if not segment:
            return

        # Nick speaks last
        candidate.nick_speaks_last = segment[-1].speaker.lower() in ("nick", "deepgram_0")

        # Turn count (speaker alternations)
        turns = 1
        for i in range(1, len(segment)):
            if segment[i].speaker != segment[i - 1].speaker:
                turns += 1
        candidate.turn_count = turns

        # Nick talk ratio
        total_words = sum(u.word_count for u in segment)
        nick_words = sum(
            u.word_count for u in segment
            if u.speaker.lower() in ("nick", "deepgram_0")
        )
        candidate.nick_talk_ratio = nick_words / max(total_words, 1)

        # Build transcript excerpt
        candidate.transcript_excerpt = _format_utterances(segment[:10])  # first 10 utterances

    async def _score_candidate(
        self, candidate: ClipCandidate, utterances: List[Utterance]
    ) -> None:
        """Score a candidate using Claude + programmatic checks."""
        # Programmatic first
        self._compute_programmatic_scores(candidate, utterances)

        # Get the segment text for Claude
        segment = [
            u for u in utterances
            if u.start >= candidate.start_time and u.end <= candidate.end_time + 2
        ]
        segment_text = _format_utterances(segment)

        prompt = self._scoring_prompt
        prompt = prompt.replace("{{CLIP_TYPE}}", candidate.clip_type)
        prompt = prompt.replace("{{PATTERN}}", candidate.pattern)
        prompt = prompt.replace("{{PRELIMINARY_SCORE}}", str(candidate.pass_trail[0].details.get("preliminary_score", "?")))
        prompt = prompt.replace("{{TRANSCRIPT_SEGMENT}}", segment_text)

        try:
            response = await self.client.complete_json(
                prompt=prompt,
                max_tokens=2048,
                temperature=0.0,
            )
            data = response.extract_json()
        except Exception as e:
            logger.warning(f"Scoring failed for {candidate.clip_id}: {e}")
            data = None

        if data and isinstance(data, dict):
            scores = data.get("scores", {})
            candidate.scores = {k: float(v) for k, v in scores.items()}
            candidate.emotional_arc = data.get("emotional_arc_description", "")
            if data.get("best_money_quote"):
                candidate.money_quote = data["best_money_quote"]

            # Check mandatory requirements
            mandatory = data.get("mandatory_requirements", {})
            all_passed = mandatory.get("all_passed", True)
            anti_patterns = data.get("anti_patterns_found", [])

            # Compute composite score (weighted)
            total_weight = sum(sw.weight for sw in self.profile.scoring_weights.values())
            weighted_sum = 0.0
            for criterion, sw in self.profile.scoring_weights.items():
                score_val = candidate.scores.get(criterion, 5.0)
                weighted_sum += score_val * sw.weight
            candidate.composite_score = (weighted_sum / total_weight) * 10  # normalize to 0-100

            # Duration bonus/penalty
            if self.profile.duration.sweet_spot_min <= candidate.duration <= self.profile.duration.sweet_spot_max:
                candidate.composite_score += 3  # bonus for sweet spot
            elif candidate.duration > self.profile.duration.max_seconds:
                candidate.composite_score -= 10

            # Nick speaks last bonus
            if candidate.nick_speaks_last:
                candidate.composite_score += 2

            candidate.pass_trail.append(PassInfo(
                pass_name="2_SCORING",
                result="SCORED",
                details={
                    "scores": candidate.scores,
                    "composite_score": round(candidate.composite_score, 1),
                    "mandatory_passed": all_passed,
                    "anti_patterns": anti_patterns,
                    "nick_speaks_last": candidate.nick_speaks_last,
                    "nick_talk_ratio": round(candidate.nick_talk_ratio, 2),
                    "turn_count": candidate.turn_count,
                    "duration": round(candidate.duration, 1),
                    "emotional_arc": candidate.emotional_arc,
                    "scoring_notes": data.get("scoring_notes", ""),
                },
            ))
        else:
            # Fallback: use preliminary score
            candidate.composite_score = candidate.pass_trail[0].details.get("preliminary_score", 5) * 10
            candidate.pass_trail.append(PassInfo(
                pass_name="2_SCORING",
                result="FALLBACK",
                details={"reason": "Claude scoring failed, using preliminary score"},
            ))

    # =========================================================================
    # STEP 4: Filter (Programmatic)
    # =========================================================================

    def _filter_candidates(self, candidates: List[ClipCandidate]) -> List[ClipCandidate]:
        """Remove candidates that fail mandatory requirements."""
        survivors = []
        for c in candidates:
            # Check dealbreaker thresholds
            failed = False
            for criterion, sw in self.profile.scoring_weights.items():
                score_val = c.scores.get(criterion, 5.0)
                if score_val < sw.dealbreaker_threshold:
                    c.pass_trail.append(PassInfo(
                        pass_name="3_FILTER",
                        result="REJECTED",
                        details={
                            "reason": f"Dealbreaker: {criterion} = {score_val} < threshold {sw.dealbreaker_threshold}",
                        },
                    ))
                    failed = True
                    break

            if failed:
                continue

            # Check scoring pass anti-patterns
            scoring_pass = next((p for p in c.pass_trail if p.pass_name == "2_SCORING"), None)
            if scoring_pass and scoring_pass.details.get("anti_patterns"):
                c.pass_trail.append(PassInfo(
                    pass_name="3_FILTER",
                    result="REJECTED",
                    details={
                        "reason": f"Anti-patterns found: {scoring_pass.details['anti_patterns']}",
                    },
                ))
                continue

            # Check mandatory requirements
            if scoring_pass and not scoring_pass.details.get("mandatory_passed", True):
                c.pass_trail.append(PassInfo(
                    pass_name="3_FILTER",
                    result="REJECTED",
                    details={"reason": "Mandatory requirements not all passed"},
                ))
                continue

            c.pass_trail.append(PassInfo(
                pass_name="3_FILTER",
                result="PASSED",
                details={"composite_score": round(c.composite_score, 1)},
            ))
            survivors.append(c)

        logger.info(f"Filter: {len(candidates)} -> {len(survivors)} candidates")
        return survivors

    # =========================================================================
    # STEP 5: Reflect (Claude with extended context)
    # =========================================================================

    async def _reflect_on_candidate(
        self, candidate: ClipCandidate, utterances: List[Utterance]
    ) -> bool:
        """Reflect on a candidate with extended context. Returns True if kept."""
        # Get context before
        context_start = max(0, candidate.start_time - self.CONTEXT_SECONDS)
        before_utts = [
            u for u in utterances
            if u.start >= context_start and u.end < candidate.start_time
        ]
        # Get the clip segment
        clip_utts = [
            u for u in utterances
            if u.start >= candidate.start_time and u.end <= candidate.end_time + 2
        ]
        # Get context after
        context_end = candidate.end_time + self.CONTEXT_SECONDS
        after_utts = [
            u for u in utterances
            if u.start > candidate.end_time and u.start < context_end
        ]

        prompt = self._reflection_prompt
        prompt = prompt.replace("{{CLIP_TYPE}}", candidate.clip_type)
        prompt = prompt.replace("{{START_TIME}}", _format_time(candidate.start_time))
        prompt = prompt.replace("{{END_TIME}}", _format_time(candidate.end_time))
        prompt = prompt.replace("{{DURATION}}", str(int(candidate.duration)))
        prompt = prompt.replace("{{SCORES}}", json.dumps(candidate.scores))
        prompt = prompt.replace("{{MONEY_QUOTE}}", candidate.money_quote)
        prompt = prompt.replace("{{REASONING}}", candidate.reasoning)
        prompt = prompt.replace("{{CONTEXT_BEFORE}}", _format_utterances(before_utts) or "(no prior context)")
        prompt = prompt.replace("{{CLIP_SEGMENT}}", _format_utterances(clip_utts))
        prompt = prompt.replace("{{CONTEXT_AFTER}}", _format_utterances(after_utts) or "(no following context)")

        try:
            response = await self.client.complete_json(
                prompt=prompt,
                max_tokens=2048,
                temperature=0.1,
            )
            data = response.extract_json()
        except Exception as e:
            logger.warning(f"Reflection failed for {candidate.clip_id}: {e}")
            candidate.pass_trail.append(PassInfo(
                pass_name="4_REFLECTION",
                result="SKIPPED",
                details={"reason": f"Reflection call failed: {e}"},
            ))
            return True  # keep on failure

        if not data or not isinstance(data, dict):
            candidate.pass_trail.append(PassInfo(
                pass_name="4_REFLECTION",
                result="SKIPPED",
                details={"reason": "No valid JSON response"},
            ))
            return True

        keep = data.get("keep_clip", True)

        # Apply boundary adjustments
        adjusted_start = data.get("adjusted_start")
        adjusted_end = data.get("adjusted_end")
        if adjusted_start and adjusted_start != "null":
            new_start = _parse_timestamp(adjusted_start)
            if new_start is not None:
                candidate.start_time = new_start
        if adjusted_end and adjusted_end != "null":
            new_end = _parse_timestamp(adjusted_end)
            if new_end is not None:
                candidate.end_time = new_end

        candidate.duration = candidate.end_time - candidate.start_time

        # Update scores if provided
        updated_scores = data.get("updated_scores", {})
        if updated_scores:
            for k, v in updated_scores.items():
                candidate.scores[k] = float(v)
            # Recompute composite
            total_weight = sum(sw.weight for sw in self.profile.scoring_weights.values())
            weighted_sum = sum(
                candidate.scores.get(c, 5.0) * sw.weight
                for c, sw in self.profile.scoring_weights.items()
            )
            candidate.composite_score = (weighted_sum / total_weight) * 10
            if self.profile.duration.sweet_spot_min <= candidate.duration <= self.profile.duration.sweet_spot_max:
                candidate.composite_score += 3
            if candidate.nick_speaks_last:
                candidate.composite_score += 2

        # Re-check programmatic metrics after boundary adjustment
        self._compute_programmatic_scores(candidate, utterances)

        candidate.pass_trail.append(PassInfo(
            pass_name="4_REFLECTION",
            result="KEPT" if keep else "REJECTED",
            details={
                "keep_clip": keep,
                "adjustment_reasoning": data.get("adjustment_reasoning", ""),
                "standalone_assessment": data.get("standalone_assessment", ""),
                "quality_change": data.get("quality_change", "same"),
                "quality_reasoning": data.get("quality_reasoning", ""),
                "better_clip_nearby": data.get("better_clip_nearby"),
                "boundary_adjusted": bool(adjusted_start or adjusted_end),
                "new_start": _format_time(candidate.start_time),
                "new_end": _format_time(candidate.end_time),
                "new_duration": round(candidate.duration, 1),
                "updated_composite": round(candidate.composite_score, 1),
                "pass_notes": data.get("pass_notes", ""),
            },
        ))

        return keep

    # =========================================================================
    # STEP 6: Debate Borderline Candidates (Multi-Agent Debate)
    # =========================================================================

    async def _debate_borderline(
        self, candidate: ClipCandidate, utterances: List[Utterance]
    ) -> bool:
        """Run advocate vs skeptic debate on a borderline candidate."""
        segment = [
            u for u in utterances
            if u.start >= candidate.start_time and u.end <= candidate.end_time + 2
        ]
        segment_text = _format_utterances(segment[:15])  # first 15 utterances for context

        proposition = (
            f"This transcript segment is a clip-worthy moment for Nick Matau's "
            f"social media channels. It is a {candidate.clip_type} clip with the "
            f"pattern '{candidate.pattern}'. The money quote is: \"{candidate.money_quote}\""
        )

        evidence = {
            "transcript_excerpt": segment_text,
            "current_scores": candidate.scores,
            "composite_score": round(candidate.composite_score, 1),
            "nick_speaks_last": candidate.nick_speaks_last,
            "nick_talk_ratio": round(candidate.nick_talk_ratio, 2),
            "turn_count": candidate.turn_count,
            "duration": round(candidate.duration, 1),
            "nick_clip_requirements": self.profile.mandatory_requirements,
            "anti_patterns_to_check": self.profile.anti_patterns,
        }

        try:
            result = await self.debate.run(proposition=proposition, evidence=evidence)
        except Exception as e:
            logger.warning(f"Debate failed for {candidate.clip_id}: {e}")
            candidate.pass_trail.append(PassInfo(
                pass_name="5_DEBATE",
                result="SKIPPED",
                details={"reason": f"Debate failed: {e}"},
            ))
            return True  # keep on failure

        keep = result.verdict != DebateVerdict.DENY or result.confidence < 0.7

        # Boost score if advocate wins convincingly
        if result.verdict == DebateVerdict.AFFIRM and result.confidence > 0.7:
            candidate.composite_score += 5
            candidate.confidence = result.confidence

        candidate.pass_trail.append(PassInfo(
            pass_name="5_DEBATE",
            result="KEPT" if keep else "REJECTED",
            details={
                "verdict": result.verdict.value,
                "confidence": round(result.confidence, 2),
                "advocate_claim": result.advocate_argument.claim,
                "advocate_evidence": result.advocate_argument.evidence[:3],
                "skeptic_claim": result.skeptic_argument.claim,
                "skeptic_evidence": result.skeptic_argument.evidence[:3],
                "judge_reasoning": result.judge_reasoning,
            },
        ))

        return keep

    # =========================================================================
    # STEP 7: Deduplicate
    # =========================================================================

    def _deduplicate(self, candidates: List[ClipCandidate]) -> List[ClipCandidate]:
        """Remove overlapping clips, keeping highest scored."""
        candidates.sort(key=lambda c: -c.composite_score)
        unique = []
        for clip in candidates:
            overlaps = False
            for kept in unique:
                overlap_start = max(clip.start_time, kept.start_time)
                overlap_end = min(clip.end_time, kept.end_time)
                overlap_duration = max(0, overlap_end - overlap_start)
                if overlap_duration > clip.duration * 0.3:
                    overlaps = True
                    break
            if not overlaps:
                unique.append(clip)
        logger.info(f"Dedup: {len(candidates)} -> {len(unique)} clips")
        return unique

    # =========================================================================
    # MAIN PIPELINE
    # =========================================================================

    async def find_clips(
        self,
        transcript_path: str,
        max_clips: int = 20,
        min_score: float = 45.0,
    ) -> List[ClipCandidate]:
        """
        Run the full 5-pass clip detection pipeline.

        Args:
            transcript_path: Path to enhanced transcript (.json or .txt)
            max_clips: Maximum clips to return
            min_score: Minimum composite score to keep

        Returns:
            Ranked list of ClipCandidates with per-pass explanations
        """
        total_start = time.time()
        logger.info(f"=== ClipFinderV3 Pipeline Start ===")
        logger.info(f"Transcript: {transcript_path}")

        # Load transcript
        utterances = self._load_transcript(transcript_path)
        logger.info(f"Loaded {len(utterances)} utterances")

        # PASS 1: Segment + Detect
        logger.info("--- PASS 1: DETECTION ---")
        windows = self._segment_transcript(utterances)
        all_candidates: List[ClipCandidate] = []

        for window in windows:
            candidates = await self._detect_candidates(window)
            all_candidates.extend(candidates)
            await asyncio.sleep(0.2)  # gentle rate limit

        logger.info(f"Pass 1 complete: {len(all_candidates)} raw candidates")

        # PASS 2: Score
        logger.info("--- PASS 2: SCORING ---")
        for cand in all_candidates:
            await self._score_candidate(cand, utterances)
            await asyncio.sleep(0.2)
        logger.info(f"Pass 2 complete: all {len(all_candidates)} scored")

        # PASS 3: Filter
        logger.info("--- PASS 3: FILTER ---")
        survivors = self._filter_candidates(all_candidates)
        # Also cut by min_score
        survivors = [c for c in survivors if c.composite_score >= min_score]
        logger.info(f"Pass 3 complete: {len(survivors)} survivors")

        # PASS 4: Reflect
        logger.info("--- PASS 4: REFLECTION ---")
        reflected = []
        for cand in survivors:
            keep = await self._reflect_on_candidate(cand, utterances)
            if keep:
                reflected.append(cand)
            await asyncio.sleep(0.2)
        logger.info(f"Pass 4 complete: {len(reflected)} after reflection")

        # PASS 5: Debate borderline
        logger.info("--- PASS 5: DEBATE ---")
        final = []
        for cand in reflected:
            if cand.composite_score < self.BORDERLINE_HIGH:
                # Borderline — debate it
                keep = await self._debate_borderline(cand, utterances)
                if keep:
                    final.append(cand)
                await asyncio.sleep(0.3)
            else:
                # High confidence — auto-pass
                cand.pass_trail.append(PassInfo(
                    pass_name="5_DEBATE",
                    result="AUTO_PASS",
                    details={"reason": f"Score {cand.composite_score:.1f} > {self.BORDERLINE_HIGH} threshold"},
                ))
                final.append(cand)
        logger.info(f"Pass 5 complete: {len(final)} after debate")

        # FINAL: Deduplicate & Rank
        final = self._deduplicate(final)
        final.sort(key=lambda c: -c.composite_score)
        final = final[:max_clips]

        # Assign final IDs
        for i, clip in enumerate(final):
            clip.clip_id = f"clip_v3_{i + 1}"

        elapsed = time.time() - total_start
        logger.info(f"=== Pipeline complete: {len(final)} clips in {elapsed:.1f}s ===")
        logger.info(f"Cost: {self.client.cost_tracker.summary()}")

        return final

    # =========================================================================
    # Save Results
    # =========================================================================

    def save_results(
        self,
        clips: List[ClipCandidate],
        output_dir: str,
        all_candidates: Optional[List[ClipCandidate]] = None,
    ) -> str:
        """
        Save results to output directory with full explanations.

        Args:
            clips: Final ranked clips
            output_dir: Directory to save results
            all_candidates: Optional list of ALL candidates (including rejected) for full report

        Returns:
            Path to the main results file
        """
        os.makedirs(output_dir, exist_ok=True)

        # Main results
        results = {
            "pipeline": "ClipFinderV3",
            "total_clips": len(clips),
            "cost": self.client.cost_tracker.summary(),
            "clips": [c.to_dict() for c in clips],
        }

        results_path = os.path.join(output_dir, "clips_v3_results.json")
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        # Human-readable report
        report_path = os.path.join(output_dir, "clips_v3_report.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("# V3 Clip Finder Results\n\n")
            f.write(f"**Total clips found**: {len(clips)}\n")
            f.write(f"**API Cost**: ${self.client.cost_tracker.total_cost:.4f}\n\n")
            f.write("---\n\n")

            for i, clip in enumerate(clips):
                f.write(f"## #{i + 1}: {clip.clip_type} — {clip.hook[:60]}\n\n")
                f.write(f"**Time**: {_format_time(clip.start_time)} to {_format_time(clip.end_time)} ({clip.duration:.0f}s)\n")
                f.write(f"**Composite Score**: {clip.composite_score:.1f}/100\n")
                f.write(f"**Pattern**: {clip.pattern}\n")
                f.write(f"**Nick's Role**: {clip.nick_role}\n")
                f.write(f"**Money Quote**: \"{clip.money_quote}\"\n")
                f.write(f"**Peak Moment**: {clip.peak_moment}\n\n")

                if clip.scores:
                    f.write("### Scores\n")
                    f.write("| Criterion | Score | Weight |\n")
                    f.write("|-----------|-------|--------|\n")
                    for criterion, sw in self.profile.scoring_weights.items():
                        score = clip.scores.get(criterion, "N/A")
                        f.write(f"| {criterion} | {score} | {sw.weight}% |\n")
                    f.write("\n")

                f.write("### Pipeline Trail\n\n")
                for p in clip.pass_trail:
                    f.write(f"**{p.pass_name}**: {p.result}\n")
                    for k, v in p.details.items():
                        if isinstance(v, (list, dict)):
                            f.write(f"  - {k}: {json.dumps(v, ensure_ascii=False)}\n")
                        else:
                            f.write(f"  - {k}: {v}\n")
                    f.write("\n")

                if clip.transcript_excerpt:
                    f.write("### Transcript Excerpt\n")
                    f.write(f"```\n{clip.transcript_excerpt}\n```\n\n")

                f.write("---\n\n")

        logger.info(f"Results saved to {output_dir}")
        return results_path


# =============================================================================
# Sync wrapper for CLI
# =============================================================================

def find_clips_sync(
    transcript_path: str,
    output_dir: str = "outputs/clips_v3",
    max_clips: int = 20,
    min_score: float = 45.0,
    profile_path: Optional[str] = None,
) -> List[ClipCandidate]:
    """Synchronous entry point for CLI usage."""
    async def _run():
        finder = ClipFinderV3(profile_path=profile_path)
        clips = await finder.find_clips(
            transcript_path=transcript_path,
            max_clips=max_clips,
            min_score=min_score,
        )
        finder.save_results(clips, output_dir)
        return clips

    return asyncio.run(_run())
