"""
Unified Clip Finder - Broad Discovery + Trim Down system.

Pass 1 (Scout): Proposes BROAD topic-covering ranges (2-5 min) that
capture the full argument on a topic. Enforces that every candidate
has real back-and-forth debate content (guest claim + Nick counter).

Pass 2 (Hard Filter): Programmatic rejection of monologues, low
back-and-forth, and clips where the guest barely speaks. Blended
ranking (LLM score + programmatic metrics) selects top candidates.

Pass 3 (Trimmer): Reads the full transcript of each broad range and
identifies KEEP vs CUT segments. Removes filler, tangents, solo rants.
The kept segments become the final clip (composite if gaps exist).
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.anthropic_client import ClaudeClient
from src.conversation_segmenter_v3 import Conversation, ConversationMap
from src.story_clip_finder import QueryIntent
from src.topic_mapper import (
    TopicMap, ConversationTopics, TopicBlock,
    TopicContinuityIndex, TopicOccurrence,
)

logger = logging.getLogger(__name__)

NICK_ALIASES = {"nick", "deepgram_0"}
SCOUT_CHUNK_DURATION = 600.0
SCOUT_CHUNK_OVERLAP = 120.0
LONG_CONVERSATION_THRESHOLD = 1200.0

MIN_NICK_RATIO = 0.15       # conversation pre-filter
MAX_NICK_RATIO = 0.85       # candidate hard filter (rejects monologues)
MIN_TURN_COUNT = 4           # candidate hard filter
MIN_GUEST_WORDS = 20         # candidate hard filter
MIN_SEGMENT_DURATION = 30.0  # seconds


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class SegmentProposal:
    """A segment within a clip (from Trimmer)."""
    start_time: float
    end_time: float
    duration: float
    purpose: str
    transcript_excerpt: str
    adjusted: bool = False
    adjustment_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TopicReference:
    """Where the same topic appears elsewhere in the conversation."""
    topic_id: str
    time_range: str
    lookup_range: str
    key_quote: str
    relationship: str
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProgrammaticScores:
    """Free-to-compute metrics from transcript data."""
    nick_speaks_last: bool = False
    nick_talk_ratio: float = 0.0
    guest_word_count: int = 0
    turn_count: int = 0
    duration_in_sweet_spot: bool = False
    composite_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def passes_hard_filter(self) -> bool:
        """Check if this candidate should survive the hard filter."""
        return (
            self.nick_talk_ratio <= MAX_NICK_RATIO
            and self.turn_count >= MIN_TURN_COUNT
            and self.guest_word_count >= MIN_GUEST_WORDS
        )


@dataclass
class FinalClip:
    """A fully trimmed and scored clip ready for extraction."""
    clip_id: str
    assembly: str
    segments: List[SegmentProposal]
    title: str
    narrative: str
    hook: str
    money_quote: str
    clip_type: str
    score: float
    standalone_coherent: bool
    boundary_adjusted: bool
    editor_notes: str
    conversation_id: str
    guest_speakers: List[str]
    topic_ids: List[str]
    query_relevance: Optional[str] = None
    scout_score: float = 0.0
    reason_for_assembly: str = ""
    topic_references: List[TopicReference] = field(default_factory=list)
    programmatic_scores: Optional[ProgrammaticScores] = None
    composite_opportunities: List[str] = field(default_factory=list)

    @property
    def total_duration(self) -> float:
        return sum(s.duration for s in self.segments)

    @property
    def start_time(self) -> float:
        return self.segments[0].start_time if self.segments else 0

    @property
    def end_time(self) -> float:
        return self.segments[-1].end_time if self.segments else 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "clip_id": self.clip_id,
            "assembly": self.assembly,
            "segments": [s.to_dict() for s in self.segments],
            "title": self.title,
            "narrative": self.narrative,
            "hook": self.hook,
            "money_quote": self.money_quote,
            "clip_type": self.clip_type,
            "score": self.score,
            "scout_score": self.scout_score,
            "standalone_coherent": self.standalone_coherent,
            "boundary_adjusted": self.boundary_adjusted,
            "editor_notes": self.editor_notes,
            "reason_for_assembly": self.reason_for_assembly,
            "conversation_id": self.conversation_id,
            "guest_speakers": self.guest_speakers,
            "topic_ids": self.topic_ids,
            "query_relevance": self.query_relevance,
            "total_duration": self.total_duration,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "topic_references": [r.to_dict() for r in self.topic_references],
            "programmatic_scores": self.programmatic_scores.to_dict() if self.programmatic_scores else None,
            "composite_opportunities": self.composite_opportunities,
        }


# =============================================================================
# HELPERS
# =============================================================================

def _load_prompt(name: str) -> str:
    prompt_dir = Path(__file__).parent.parent / "prompts"
    path = prompt_dir / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8")


_TS_RE = re.compile(r"(\d+):(\d+):(\d+)")


def _parse_timestamp(ts: str) -> Optional[float]:
    ts = ts.strip().strip("[]")
    m = _TS_RE.search(ts)
    if not m:
        return None
    h, mn, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return h * 3600 + mn * 60 + s


def _format_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h}:{m:02d}:{s:02d}"


def _get_conversation_transcript(
    utterances: List[Dict], conv: Conversation,
) -> str:
    lines = []
    for idx in conv.utterance_indices:
        if idx >= len(utterances):
            continue
        u = utterances[idx]
        ts = _format_time(u["start"])
        lines.append(f"[{ts}] {u['speaker']}: {u['text']}")
    return "\n".join(lines)


def _get_range_transcript(
    utterances: List[Dict], start: float, end: float,
) -> str:
    lines = []
    for u in utterances:
        if u["start"] >= start and u["start"] <= end:
            ts = _format_time(u["start"])
            lines.append(f"[{ts}] {u['speaker']}: {u['text']}")
    return "\n".join(lines)


def _get_range_utterances(
    utterances: List[Dict], start: float, end: float,
) -> List[Dict]:
    return [u for u in utterances if u["start"] >= start and u["start"] <= end]


def _build_topic_map_section(conv_topics: Optional[ConversationTopics]) -> str:
    if not conv_topics or not conv_topics.topics:
        return "(no topic map available)"
    lines = []
    for t in conv_topics.topics:
        lines.append(
            f"- [{_format_time(t.start_time)}-{_format_time(t.end_time)}] "
            f"{t.topic_name} ({t.topic_id}) [{t.sentiment}]"
        )
    return "\n".join(lines)


def _build_topic_recurrence_section(
    conv_id: str, continuity: Optional[TopicContinuityIndex],
) -> str:
    if not continuity:
        return ""
    recurrences = continuity.get_recurrences(conv_id)
    if not recurrences:
        return ""
    lines = [
        "\n## TOPIC RECURRENCE IN THIS CONVERSATION",
        "These topics appear more than once -- they are composite clip candidates:",
    ]
    for tid, occs in recurrences.items():
        ranges = " AND ".join(
            f"[{_format_time(o.start_time)}-{_format_time(o.end_time)}]"
            for o in sorted(occs, key=lambda x: x.start_time)
        )
        lines.append(f"- {tid}: {ranges}")
        sentiments = [o.sentiment for o in occs]
        if "heated" in sentiments or "confrontational" in sentiments:
            lines.append("  -> Escalation potential. Consider stitching the strongest segments.")
        else:
            lines.append("  -> Topic returns. Evaluate whether combining segments adds value.")
    return "\n".join(lines) + "\n"


def _build_topic_continuity_trimmer_section(
    topic_ids: List[str],
    conv_id: str,
    clip_start: float,
    clip_end: float,
    continuity: Optional[TopicContinuityIndex],
) -> str:
    if not continuity or not topic_ids:
        return ""
    conv_topics = continuity.by_conversation.get(conv_id, {})
    if not conv_topics:
        return ""
    lines = ["\n## TOPIC CONTINUITY (same topics elsewhere in this conversation)"]
    found_any = False
    for tid in topic_ids:
        occs = conv_topics.get(tid, [])
        other_occs = [
            o for o in occs
            if not (o.start_time >= clip_start - 5 and o.end_time <= clip_end + 5)
        ]
        if not other_occs:
            continue
        found_any = True
        lines.append(f"\n**{tid}** also appears at:")
        for o in sorted(other_occs, key=lambda x: x.start_time):
            quote_part = f' -- "{o.key_quote}"' if o.key_quote else ""
            lines.append(
                f"- [{_format_time(o.start_time)}-{_format_time(o.end_time)}] "
                f"[{o.sentiment}]{quote_part}"
            )
    if not found_any:
        return ""
    return "\n".join(lines) + "\n"


def _build_query_section(intent: Optional[QueryIntent]) -> str:
    if intent is None:
        return ""
    lines = ["\n## USER'S SEARCH REQUEST"]
    if intent.topic:
        lines.append(f'The user is looking for: "{intent.topic}"')
        lines.append("PRIORITIZE clips related to this topic. +2 to score for relevant clips.")
    if hasattr(intent, "search_targets") and intent.search_targets:
        lines.append("\nSPECIFIC MOMENTS TO FIND:")
        for t in intent.search_targets:
            lines.append(f"- {t.label}: {t.description}")
    if hasattr(intent, "raw_query") and intent.raw_query:
        lines.append(f'\nOriginal request: "{intent.raw_query}"')
    return "\n".join(lines) + "\n"


# =============================================================================
# PROGRAMMATIC SCORING + HARD FILTER
# =============================================================================

def _compute_programmatic_scores(
    utterances: List[Dict],
    start_time: float,
    end_time: float,
) -> ProgrammaticScores:
    """Compute free metrics from transcript data for a clip range."""
    segment = _get_range_utterances(utterances, start_time, end_time)
    if not segment:
        return ProgrammaticScores()

    nick_words = 0
    guest_words = 0
    total_words = 0
    turns = 0
    last_speaker = None
    last_speaker_is_nick = False

    for u in segment:
        wc = u.get("word_count", len(u.get("text", "").split()))
        total_words += wc
        is_nick = u["speaker"].lower() in NICK_ALIASES
        if is_nick:
            nick_words += wc
        else:
            guest_words += wc
        if u["speaker"] != last_speaker:
            turns += 1
            last_speaker = u["speaker"]
        last_speaker_is_nick = is_nick

    nick_ratio = nick_words / max(total_words, 1)
    duration = end_time - start_time
    in_sweet_spot = 60 <= duration <= 180

    score = 0.0
    score += 20 if last_speaker_is_nick else 0
    if 0.45 <= nick_ratio <= 0.75:
        score += 25
    elif nick_ratio <= MAX_NICK_RATIO:
        score += 15
    else:
        score += 0
    score += min(25, turns * 2.5)
    score += 15 if in_sweet_spot else (8 if 30 <= duration <= 300 else 0)
    score += 15 if guest_words >= 30 else (5 if guest_words >= MIN_GUEST_WORDS else 0)

    return ProgrammaticScores(
        nick_speaks_last=last_speaker_is_nick,
        nick_talk_ratio=round(nick_ratio, 3),
        guest_word_count=guest_words,
        turn_count=turns,
        duration_in_sweet_spot=in_sweet_spot,
        composite_score=round(min(100, score), 1),
    )


def _compute_conversation_energy(
    utterances: List[Dict], conv: Conversation,
) -> Tuple[float, int]:
    nick_words = 0
    total_words = 0
    turns = 0
    last_speaker = None
    for idx in conv.utterance_indices:
        if idx >= len(utterances):
            continue
        u = utterances[idx]
        wc = u.get("word_count", len(u.get("text", "").split()))
        total_words += wc
        if u["speaker"].lower() in NICK_ALIASES:
            nick_words += wc
        if u["speaker"] != last_speaker:
            turns += 1
            last_speaker = u["speaker"]
    nick_ratio = nick_words / max(total_words, 1)
    return nick_ratio, turns


def _hard_filter_candidate(
    raw: Dict[str, Any], utterances: List[Dict],
) -> Tuple[bool, ProgrammaticScores, str]:
    """Hard-filter a scout candidate. Returns (passed, scores, reason)."""
    segments_raw = raw.get("segments", [])
    if not segments_raw:
        return False, ProgrammaticScores(), "no segments"

    earliest = None
    latest = None
    for seg in segments_raw:
        start = _parse_timestamp(seg.get("start_time", ""))
        end = _parse_timestamp(seg.get("end_time", ""))
        if start is None or end is None:
            continue
        if earliest is None or start < earliest:
            earliest = start
        if latest is None or end > latest:
            latest = end

    if earliest is None or latest is None:
        return False, ProgrammaticScores(), "invalid timestamps"

    dur = latest - earliest
    if dur < MIN_SEGMENT_DURATION:
        return False, ProgrammaticScores(), f"too short ({dur:.0f}s < {MIN_SEGMENT_DURATION}s)"

    prog = _compute_programmatic_scores(utterances, earliest, latest)

    if prog.nick_talk_ratio > MAX_NICK_RATIO:
        return False, prog, f"monologue (nick_ratio={prog.nick_talk_ratio:.0%})"
    if prog.turn_count < MIN_TURN_COUNT:
        return False, prog, f"not enough back-and-forth (turns={prog.turn_count})"
    if prog.guest_word_count < MIN_GUEST_WORDS:
        return False, prog, f"guest barely spoke ({prog.guest_word_count} words)"

    if not raw.get("guest_claim"):
        return False, prog, "no guest_claim specified"

    return True, prog, "passed"


def _compute_blended_score(raw: Dict[str, Any], prog: ProgrammaticScores) -> float:
    """Blend scout LLM score with programmatic metrics for ranking."""
    scout_score = float(raw.get("preliminary_score", 0))
    return (scout_score * 6) + (prog.composite_score / 10 * 4)


# =============================================================================
# TOPIC REFERENCE BUILDER
# =============================================================================

def _build_topic_references_for_clip(
    topic_ids: List[str],
    conv_id: str,
    clip_start: float,
    clip_end: float,
    continuity: Optional[TopicContinuityIndex],
) -> List[TopicReference]:
    if not continuity or not topic_ids:
        return []
    conv_topics = continuity.by_conversation.get(conv_id, {})
    refs: List[TopicReference] = []
    padding = 30.0
    for tid in topic_ids:
        occs = conv_topics.get(tid, [])
        for occ in occs:
            if occ.start_time >= clip_start - 5 and occ.end_time <= clip_end + 5:
                continue
            refs.append(TopicReference(
                topic_id=tid,
                time_range=f"[{_format_time(occ.start_time)}-{_format_time(occ.end_time)}]",
                lookup_range=(
                    f"[{_format_time(max(0, occ.start_time - padding))}-"
                    f"{_format_time(occ.end_time + padding)}]"
                ),
                key_quote=occ.key_quote,
                relationship=_infer_relationship(occ, clip_start),
            ))
    return refs


def _infer_relationship(occ: TopicOccurrence, clip_start: float) -> str:
    if occ.start_time > clip_start:
        if occ.sentiment in ("heated", "confrontational"):
            return "escalation"
        return "continuation"
    if occ.sentiment in ("heated", "confrontational"):
        return "prior_confrontation"
    return "prior_mention"


# =============================================================================
# UNIFIED CLIP FINDER
# =============================================================================

class ClipFinderUnified:
    """
    Broad Discovery + Trim Down clip finder.

    Scout proposes broad ranges, hard filter rejects monologues,
    Trimmer cuts fluff to leave only substantive back-and-forth.
    """

    MIN_CONVERSATION_DURATION = 90.0
    MAX_TRANSCRIPT_CHARS = 90000

    def __init__(self, client: Optional[ClaudeClient] = None):
        self.client = client or ClaudeClient()
        self._scout_prompt = _load_prompt("clip_scout.md")
        self._trimmer_prompt = _load_prompt("clip_trimmer.md")
        logger.info("ClipFinderUnified initialized")

    # -----------------------------------------------------------------
    # PASS 1: SCOUT
    # -----------------------------------------------------------------

    def _chunk_conversation_for_scout(
        self, conv: Conversation, utterances: List[Dict],
    ) -> List[Tuple[float, float, str]]:
        if conv.duration <= LONG_CONVERSATION_THRESHOLD:
            text = _get_conversation_transcript(utterances, conv)
            return [(conv.start_time, conv.end_time, text)]
        chunks = []
        start = conv.start_time
        while start < conv.end_time:
            end = min(start + SCOUT_CHUNK_DURATION, conv.end_time)
            text = _get_range_transcript(utterances, start, end)
            if text.strip():
                chunks.append((start, end, text))
            start += SCOUT_CHUNK_DURATION - SCOUT_CHUNK_OVERLAP
        logger.info(
            f"  {conv.id}: split into {len(chunks)} scout chunks "
            f"({conv.duration / 60:.0f}min conversation)"
        )
        return chunks

    async def _scout_conversation(
        self,
        conv: Conversation,
        transcript_text: str,
        conv_topics: Optional[ConversationTopics],
        intent: Optional[QueryIntent],
        continuity: Optional[TopicContinuityIndex],
    ) -> List[Dict[str, Any]]:
        topic_section = _build_topic_map_section(conv_topics)
        recurrence_section = _build_topic_recurrence_section(conv.id, continuity)
        query_section = _build_query_section(intent)

        if len(transcript_text) > self.MAX_TRANSCRIPT_CHARS:
            transcript_text = transcript_text[:self.MAX_TRANSCRIPT_CHARS] + "\n[... truncated ...]"

        prompt = self._scout_prompt
        prompt = prompt.replace("{{CONVERSATION_ID}}", conv.id)
        prompt = prompt.replace("{{GUEST_SPEAKERS}}", ", ".join(conv.guest_speakers[:4]))
        prompt = prompt.replace("{{DURATION}}", f"{conv.duration / 60:.0f} minutes")
        prompt = prompt.replace("{{TOPIC_MAP}}", topic_section)
        prompt = prompt.replace("{{TOPIC_RECURRENCE_SECTION}}", recurrence_section)
        prompt = prompt.replace("{{QUERY_SECTION}}", query_section)
        prompt = prompt.replace("{{TRANSCRIPT}}", transcript_text)

        try:
            response = await self.client.complete_json(
                prompt=prompt,
                max_tokens=8192,
                temperature=0.2,
            )
            data = response.extract_json()
        except Exception as e:
            logger.warning(f"Scout failed for {conv.id}: {e}")
            return []

        if not data or not isinstance(data, list):
            return []

        for raw in data:
            raw["_conversation_id"] = conv.id
            raw["_guest_speakers"] = conv.guest_speakers[:4]

        logger.info(f"  Scout {conv.id}: {len(data)} candidates")
        return data

    # -----------------------------------------------------------------
    # PASS 3: TRIMMER
    # -----------------------------------------------------------------

    async def _trim_candidate(
        self,
        raw: Dict[str, Any],
        prog: ProgrammaticScores,
        utterances: List[Dict],
        conv_topics: Optional[ConversationTopics],
        intent: Optional[QueryIntent],
        continuity: Optional[TopicContinuityIndex],
        candidate_idx: int,
    ) -> Optional[FinalClip]:
        """Send the full broad range to the trimmer to cut fluff."""
        segments_raw = raw.get("segments", [])
        if not segments_raw:
            return None

        earliest = None
        latest = None
        for seg in segments_raw:
            start = _parse_timestamp(seg.get("start_time", ""))
            end = _parse_timestamp(seg.get("end_time", ""))
            if start is None or end is None:
                continue
            if earliest is None or start < earliest:
                earliest = start
            if latest is None or end > latest:
                latest = end

        if earliest is None or latest is None:
            return None

        full_transcript = _get_range_transcript(utterances, earliest, latest)
        if not full_transcript.strip():
            return None

        topic_ids = raw.get("topic_ids", [])
        conv_id = raw.get("_conversation_id", "unknown")

        topic_cont_section = _build_topic_continuity_trimmer_section(
            topic_ids, conv_id, earliest, latest, continuity,
        )
        query_section = _build_query_section(intent)

        topic_str = ", ".join(topic_ids) if topic_ids else raw.get("clip_type", "unknown")

        prompt = self._trimmer_prompt
        prompt = prompt.replace("{{CLIP_TYPE}}", raw.get("clip_type", "UNKNOWN"))
        prompt = prompt.replace("{{TOPIC}}", topic_str)
        prompt = prompt.replace("{{GUEST_CLAIM}}", raw.get("guest_claim", "(not specified)"))
        prompt = prompt.replace("{{HOOK}}", raw.get("hook", ""))
        prompt = prompt.replace("{{MONEY_QUOTE}}", raw.get("money_quote", ""))
        prompt = prompt.replace("{{SCOUT_SCORE}}", str(raw.get("preliminary_score", "?")))
        prompt = prompt.replace("{{FULL_TRANSCRIPT}}", full_transcript)
        prompt = prompt.replace("{{TOPIC_CONTINUITY_SECTION}}", topic_cont_section)
        prompt = prompt.replace("{{QUERY_SECTION}}", query_section)

        try:
            response = await self.client.complete_json(
                prompt=prompt,
                max_tokens=4096,
                temperature=0.0,
            )
            result = response.extract_json()
        except Exception as e:
            logger.warning(f"Trimmer failed for candidate {candidate_idx}: {e}")
            return self._build_clip_from_scout(raw, prog, utterances, continuity, candidate_idx)

        if not result or not isinstance(result, dict):
            return self._build_clip_from_scout(raw, prog, utterances, continuity, candidate_idx)

        verdict = result.get("verdict", "approve")
        if verdict == "reject":
            logger.info(f"  Trimmer rejected {candidate_idx}: {result.get('trimmer_notes', '')[:80]}")
            return None

        keep_segments = result.get("keep_segments", [])
        if not keep_segments:
            return self._build_clip_from_scout(raw, prog, utterances, continuity, candidate_idx)

        final_segments: List[SegmentProposal] = []
        for kseg in keep_segments:
            start = _parse_timestamp(kseg.get("start_time", ""))
            end = _parse_timestamp(kseg.get("end_time", ""))
            if start is None or end is None:
                continue
            dur = end - start
            if dur < 15:
                continue
            final_segments.append(SegmentProposal(
                start_time=start,
                end_time=end,
                duration=round(dur, 2),
                purpose=kseg.get("purpose", "exchange"),
                transcript_excerpt=kseg.get("what_happens", ""),
            ))

        if not final_segments:
            return self._build_clip_from_scout(raw, prog, utterances, continuity, candidate_idx)

        # Merge segments that are very close together (< 10s gap)
        merged: List[SegmentProposal] = [final_segments[0]]
        for seg in final_segments[1:]:
            prev = merged[-1]
            gap = seg.start_time - prev.end_time
            if gap < 10:
                prev.end_time = seg.end_time
                prev.duration = round(prev.end_time - prev.start_time, 2)
                if seg.purpose in ("knockout", "nick_counter"):
                    prev.purpose = seg.purpose
            else:
                merged.append(seg)
        final_segments = merged

        total_kept = sum(s.duration for s in final_segments)
        if total_kept < 30:
            logger.info(f"  Trimmer: candidate {candidate_idx} too short after trim ({total_kept:.0f}s)")
            return None

        assembly = "continuous" if len(final_segments) == 1 else "composite"

        final_prog = _compute_programmatic_scores(
            utterances, final_segments[0].start_time, final_segments[-1].end_time,
        )
        topic_refs = _build_topic_references_for_clip(
            topic_ids, conv_id,
            final_segments[0].start_time, final_segments[-1].end_time,
            continuity,
        )

        final_score = result.get("final_score", raw.get("preliminary_score", 5))
        composite_opps = []
        raw_opp = raw.get("composite_opportunity")
        if raw_opp:
            composite_opps.append(raw_opp)

        if conv_topics and not topic_ids:
            for seg in final_segments:
                for tb in conv_topics.topics:
                    if seg.start_time >= tb.start_time and seg.start_time < tb.end_time:
                        if tb.topic_id not in topic_ids:
                            topic_ids.append(tb.topic_id)

        clip = FinalClip(
            clip_id=f"unified_{candidate_idx}",
            assembly=assembly,
            segments=final_segments,
            title=result.get("title", raw.get("hook", "Untitled")[:60]),
            narrative=result.get("narrative", ""),
            hook=result.get("hook", raw.get("hook", "")),
            money_quote=result.get("money_quote", raw.get("money_quote", "")),
            clip_type=raw.get("clip_type", "UNKNOWN"),
            score=round(float(final_score), 1),
            standalone_coherent=True,
            boundary_adjusted=True,
            editor_notes=result.get("trimmer_notes", ""),
            conversation_id=conv_id,
            guest_speakers=raw.get("_guest_speakers", []),
            topic_ids=topic_ids,
            query_relevance=raw.get("query_relevance"),
            scout_score=float(raw.get("preliminary_score", 0)),
            reason_for_assembly=raw.get("reason_for_assembly", ""),
            topic_references=topic_refs,
            programmatic_scores=final_prog,
            composite_opportunities=composite_opps,
        )

        seg_info = f"{len(final_segments)} segs, {total_kept:.0f}s kept"
        logger.info(
            f"  Trimmer approved {candidate_idx}: '{clip.title[:40]}' "
            f"({assembly}, {clip.score}/10, {seg_info})"
        )
        return clip

    def _build_clip_from_scout(
        self,
        raw: Dict[str, Any],
        prog: ProgrammaticScores,
        utterances: List[Dict],
        continuity: Optional[TopicContinuityIndex],
        candidate_idx: int,
    ) -> FinalClip:
        """Build a FinalClip from scout data when trimmer fails."""
        segments_raw = raw.get("segments", [])
        segments = []
        for seg in segments_raw:
            start = _parse_timestamp(seg.get("start_time", ""))
            end = _parse_timestamp(seg.get("end_time", ""))
            if start is None or end is None:
                continue
            dur = end - start
            if dur < 15:
                continue
            segments.append(SegmentProposal(
                start_time=start, end_time=end,
                duration=round(dur, 2),
                purpose=seg.get("purpose", "full_clip"),
                transcript_excerpt=seg.get("transcript_excerpt", ""),
            ))

        if not segments:
            segments = [SegmentProposal(0, 30, 30, "full_clip", "")]

        assembly = raw.get("assembly", "continuous")
        score = float(raw.get("preliminary_score", 5)) * 0.7

        topic_ids = raw.get("topic_ids", [])
        conv_id = raw.get("_conversation_id", "unknown")
        topic_refs = _build_topic_references_for_clip(
            topic_ids, conv_id, segments[0].start_time,
            segments[-1].end_time, continuity,
        )

        return FinalClip(
            clip_id=f"unified_{candidate_idx}",
            assembly=assembly,
            segments=segments,
            title=raw.get("hook", "Untitled")[:60],
            narrative="",
            hook=raw.get("hook", ""),
            money_quote=raw.get("money_quote", ""),
            clip_type=raw.get("clip_type", "UNKNOWN"),
            score=round(score, 1),
            standalone_coherent=True,
            boundary_adjusted=False,
            editor_notes="Trimmer failed -- using scout boundaries (penalized)",
            conversation_id=conv_id,
            guest_speakers=raw.get("_guest_speakers", []),
            topic_ids=topic_ids,
            scout_score=float(raw.get("preliminary_score", 0)),
            reason_for_assembly=raw.get("reason_for_assembly", ""),
            topic_references=topic_refs,
            programmatic_scores=prog,
            composite_opportunities=[],
        )

    # -----------------------------------------------------------------
    # MAIN PIPELINE
    # -----------------------------------------------------------------

    async def find_clips(
        self,
        transcript_path: str,
        conv_map: ConversationMap,
        topic_map: Optional[TopicMap] = None,
        intent: Optional[QueryIntent] = None,
        max_clips: int = 15,
    ) -> List[FinalClip]:
        """Run the full pipeline: scout -> hard filter -> rank -> trim -> quality gate."""
        total_start = time.time()
        logger.info("=== ClipFinderUnified Pipeline Start ===")
        if intent:
            logger.info(f"Query: '{intent.raw_query}' (type={intent.query_type})")

        with open(transcript_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        utterances = data.get("utterances", [])
        logger.info(f"Loaded {len(utterances)} utterances")

        topic_lookup: Dict[str, ConversationTopics] = {}
        continuity: Optional[TopicContinuityIndex] = None
        if topic_map:
            for ct in topic_map.conversations:
                topic_lookup[ct.conversation_id] = ct
            continuity = topic_map.continuity_index

        # --- PHASE 0: FILTER CONVERSATIONS ---
        eligible = [
            c for c in conv_map.conversations
            if c.duration >= self.MIN_CONVERSATION_DURATION
        ]

        if intent and not intent.cross_conversation and intent.target_conversation:
            target = intent.target_conversation.lower()
            matched = [c for c in eligible if c.id.lower() == target]
            if not matched:
                target_words = set(re.findall(r"[a-z]+", target))
                scored = []
                for c in eligible:
                    hints = set(h.lower() for h in c.topic_hint)
                    scored.append((c, len(target_words & hints)))
                scored.sort(key=lambda x: x[1], reverse=True)
                if scored and scored[0][1] > 0:
                    matched = [scored[0][0]]
            if matched:
                eligible = matched

        pre_filter_count = len(eligible)
        filtered_eligible = []
        for conv in eligible:
            nick_ratio, turns = _compute_conversation_energy(utterances, conv)
            if nick_ratio < MIN_NICK_RATIO or turns < 3:
                logger.info(f"  Skipping {conv.id} (nick_ratio={nick_ratio:.2f}, turns={turns})")
                continue
            filtered_eligible.append(conv)
        eligible = filtered_eligible
        logger.info(f"Pre-filter: {pre_filter_count} -> {len(eligible)} conversations")

        # --- PASS 1: SCOUT ---
        logger.info("--- PASS 1: SCOUT ---")
        all_proposals: List[Dict[str, Any]] = []

        for conv in eligible:
            conv_topics = topic_lookup.get(conv.id)
            chunks = self._chunk_conversation_for_scout(conv, utterances)

            for chunk_start, chunk_end, chunk_text in chunks:
                if len(chunk_text) < 200:
                    continue
                proposals = await self._scout_conversation(
                    conv, chunk_text, conv_topics, intent, continuity,
                )
                all_proposals.extend(proposals)
                await asyncio.sleep(0.3)

        logger.info(f"Scout complete: {len(all_proposals)} total candidates")

        # --- PASS 2: HARD FILTER + BLENDED RANK ---
        logger.info("--- PASS 2: HARD FILTER ---")
        scored_candidates: List[Tuple[Dict[str, Any], ProgrammaticScores, float]] = []
        rejected_count = 0

        for raw in all_proposals:
            passed, prog, reason = _hard_filter_candidate(raw, utterances)
            if not passed:
                rejected_count += 1
                continue
            blended = _compute_blended_score(raw, prog)
            scored_candidates.append((raw, prog, blended))

        scored_candidates.sort(key=lambda x: -x[2])
        candidates_for_trim = scored_candidates[:max_clips * 5]

        logger.info(
            f"Hard filter: {len(all_proposals)} -> {len(scored_candidates)} "
            f"({rejected_count} rejected). "
            f"Sending top {len(candidates_for_trim)} to trimmer."
        )

        # --- PASS 3: TRIMMER ---
        logger.info(f"--- PASS 3: TRIMMER ({len(candidates_for_trim)} candidates) ---")
        final_clips: List[FinalClip] = []

        for i, (raw, prog, blended) in enumerate(candidates_for_trim):
            conv_id = raw.get("_conversation_id", "")
            conv_topics = topic_lookup.get(conv_id)

            clip = await self._trim_candidate(
                raw, prog, utterances, conv_topics, intent, continuity, i + 1,
            )
            if clip:
                final_clips.append(clip)
            await asyncio.sleep(0.2)

        # --- QUALITY GATE ---
        final_clips = self._deduplicate(final_clips)
        final_clips.sort(key=lambda c: -c.score)
        final_clips = final_clips[:max_clips]

        for i, clip in enumerate(final_clips):
            clip.clip_id = f"clip_{i + 1}"

        elapsed = time.time() - total_start
        logger.info(f"=== ClipFinderUnified Complete: {len(final_clips)} clips in {elapsed:.1f}s ===")
        logger.info(f"Cost: {self.client.cost_tracker.summary()}")

        return final_clips

    def _deduplicate(self, clips: List[FinalClip]) -> List[FinalClip]:
        clips.sort(key=lambda c: -c.score)
        unique: List[FinalClip] = []
        for clip in clips:
            overlaps = False
            for kept in unique:
                if clip.conversation_id != kept.conversation_id:
                    continue
                for seg_a in clip.segments:
                    for seg_b in kept.segments:
                        overlap_start = max(seg_a.start_time, seg_b.start_time)
                        overlap_end = min(seg_a.end_time, seg_b.end_time)
                        overlap_dur = max(0, overlap_end - overlap_start)
                        if overlap_dur > seg_a.duration * 0.3:
                            overlaps = True
                            break
                    if overlaps:
                        break
                if overlaps:
                    break
            if not overlaps:
                unique.append(clip)
        return unique

    # -----------------------------------------------------------------
    # SAVE RESULTS
    # -----------------------------------------------------------------

    def save_results(
        self,
        clips: List[FinalClip],
        output_dir: str,
        intent: Optional[QueryIntent] = None,
        topic_map: Optional[TopicMap] = None,
    ) -> None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        results = {
            "total_clips": len(clips),
            "query": intent.to_dict() if intent else None,
            "clips": [c.to_dict() for c in clips],
        }
        json_path = out / "unified_clips_results.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        lines = ["# Unified Clip Finder Report\n"]
        if intent:
            lines.append(f"**Query:** {intent.raw_query}")
            if intent.topic:
                lines.append(f"**Topic:** {intent.topic}")
            lines.append("")

        continuous = sum(1 for c in clips if c.assembly == "continuous")
        composite = sum(1 for c in clips if c.assembly == "composite")
        lines.append(f"**Total clips:** {len(clips)} ({continuous} continuous, {composite} composite)\n")

        for i, clip in enumerate(clips, 1):
            lines.append(f"---\n## Clip {i}: {clip.title}\n")
            lines.append(f"- **Type:** {clip.clip_type}")
            lines.append(f"- **Assembly:** {clip.assembly}")
            lines.append(f"- **Score:** {clip.score}/10 (scout: {clip.scout_score}/10)")
            lines.append(f"- **Conversation:** {clip.conversation_id}")
            lines.append(f"- **Guests:** {', '.join(clip.guest_speakers)}")
            lines.append(f"- **Duration:** {clip.total_duration:.0f}s")
            if clip.topic_ids:
                lines.append(f"- **Topics:** {', '.join(clip.topic_ids)}")
            if clip.programmatic_scores:
                ps = clip.programmatic_scores
                lines.append(
                    f"- **Metrics:** nick_ratio={ps.nick_talk_ratio:.0%}, "
                    f"guest_words={ps.guest_word_count}, "
                    f"turns={ps.turn_count}, "
                    f"nick_last={ps.nick_speaks_last}"
                )
            if clip.query_relevance:
                lines.append(f"- **Query relevance:** {clip.query_relevance}")
            lines.append(f"\n**Hook:** {clip.hook}")
            lines.append(f"**Money quote:** {clip.money_quote}")
            if clip.narrative:
                lines.append(f"**Narrative:** {clip.narrative}")
            if clip.reason_for_assembly and clip.assembly == "composite":
                lines.append(f"**Why composite:** {clip.reason_for_assembly}")
            if clip.editor_notes:
                lines.append(f"**Trimmer notes:** {clip.editor_notes}")

            lines.append("\n**Segments:**\n")
            for j, seg in enumerate(clip.segments, 1):
                lines.append(
                    f"{j}. **{seg.purpose.upper()}** "
                    f"[{_format_time(seg.start_time)} - {_format_time(seg.end_time)}] "
                    f"({seg.duration:.0f}s)"
                )
                if seg.transcript_excerpt:
                    lines.append(f"   *{seg.transcript_excerpt}*")

            if clip.topic_references:
                lines.append("\n**Topic References (same topic elsewhere):**\n")
                for ref in clip.topic_references:
                    lines.append(
                        f"- **{ref.topic_id}** {ref.time_range} "
                        f"(lookup: {ref.lookup_range}) [{ref.relationship}]"
                    )
                    if ref.key_quote:
                        lines.append(f"  *\"{ref.key_quote}\"*")

            if clip.composite_opportunities:
                lines.append("\n**Composite Opportunities:**\n")
                for opp in clip.composite_opportunities:
                    lines.append(f"- {opp}")

            lines.append("")

        md_path = out / "unified_clips_report.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        logger.info(f"Results saved to {out}")


# =============================================================================
# SYNC ENTRY POINT
# =============================================================================

def find_clips_unified_sync(
    transcript_path: str,
    conv_map: ConversationMap,
    output_dir: str = "outputs/clips_unified",
    topic_map: Optional[TopicMap] = None,
    query: Optional[str] = None,
    max_clips: int = 15,
) -> List[FinalClip]:
    """Synchronous entry point for CLI usage."""
    async def _run():
        finder = ClipFinderUnified()
        intent = None
        if query:
            from src.story_clip_finder import StoryClipFinder
            sf = StoryClipFinder(client=finder.client)
            intent = await sf.interpret_query(query, conv_map)
        clips = await finder.find_clips(
            transcript_path, conv_map, topic_map, intent, max_clips,
        )
        finder.save_results(clips, output_dir, intent, topic_map)
        return clips
    return asyncio.run(_run())
