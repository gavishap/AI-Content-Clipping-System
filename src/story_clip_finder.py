"""
Story Clip Finder - Composite clip detection with free-form query support.

Finds thematic connections within conversations (contradictions, gotcha arcs,
escalations) and proposes multi-segment "story clips" that can be stitched
into a single video. Supports optional free-form natural language queries
that steer what the AI looks for.
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

logger = logging.getLogger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class SearchTarget:
    """A specific moment the user wants found."""
    description: str
    label: str
    role_in_story: str  # "setup" | "payoff" | "contrast" | "evidence" | "any"


@dataclass
class QueryIntent:
    """Structured interpretation of a free-form user query."""
    raw_query: str
    query_type: str  # topic_search, moment_search, comparison, narrative, conversation_target, cross_conversation, open_ended
    topic: Optional[str] = None
    target_conversation: Optional[str] = None
    search_targets: List[SearchTarget] = field(default_factory=list)
    assembly_instruction: Optional[str] = None
    output_preference: str = "auto"
    cross_conversation: bool = True

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QueryIntent":
        targets = [
            SearchTarget(**t) for t in data.get("search_targets", [])
        ]
        return cls(
            raw_query=data.get("raw_query", ""),
            query_type=data.get("query_type", "topic_search"),
            topic=data.get("topic"),
            target_conversation=data.get("target_conversation"),
            search_targets=targets,
            assembly_instruction=data.get("assembly_instruction"),
            output_preference=data.get("output_preference", "auto"),
            cross_conversation=data.get("cross_conversation", True),
        )


@dataclass
class ClipSegment:
    """A single segment within a story clip."""
    start_time: float
    end_time: float
    duration: float
    purpose: str
    transcript_excerpt: str
    matches_target: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Topic:
    """A topic extracted from a conversation."""
    name: str
    start_time: float
    end_time: float
    key_quotes: List[str]
    relevance_to_query: Optional[str] = None


@dataclass
class StoryClip:
    """A composite clip made of multiple non-contiguous segments."""
    story_id: str
    conversation_id: str
    guest_speakers: List[str]
    story_type: str
    title: str
    narrative: str
    segments: List[ClipSegment]
    total_duration: float
    score: float
    reasoning: str
    query_intent: Optional[QueryIntent] = None
    query_relevance: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "story_id": self.story_id,
            "conversation_id": self.conversation_id,
            "guest_speakers": self.guest_speakers,
            "story_type": self.story_type,
            "title": self.title,
            "narrative": self.narrative,
            "segments": [s.to_dict() for s in self.segments],
            "total_duration": self.total_duration,
            "score": self.score,
            "reasoning": self.reasoning,
            "query_relevance": self.query_relevance,
        }
        if self.query_intent:
            d["query"] = self.query_intent.raw_query
        return d


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
    """Parse [HH:MM:SS] or HH:MM:SS into seconds."""
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


def _build_conversation_summary(conv_map: ConversationMap) -> str:
    """Build a compact text summary of conversations for the query interpreter."""
    lines = []
    for c in conv_map.conversations:
        guests = ", ".join(c.guest_speakers[:3])
        dur_min = c.duration / 60
        hints = ", ".join(c.topic_hint[:5])
        lines.append(
            f"- {c.id}: {_format_time(c.start_time)}-{_format_time(c.end_time)} "
            f"({dur_min:.0f}min) guests=[{guests}] topics=[{hints}]"
        )
    return "\n".join(lines)


def _get_conversation_transcript(
    utterances: List[Dict],
    conv: Conversation,
) -> str:
    """Extract the formatted transcript for a single conversation."""
    lines = []
    for idx in conv.utterance_indices:
        if idx >= len(utterances):
            continue
        u = utterances[idx]
        ts = _format_time(u["start"])
        lines.append(f"[{ts}] {u['speaker']}: {u['text']}")
    return "\n".join(lines)


# =============================================================================
# STORY CLIP FINDER
# =============================================================================

class StoryClipFinder:
    """
    Finds thematic connections within conversations and proposes composite clips.

    Supports an optional QueryIntent that changes what every AI pass looks for.

    Usage:
        finder = StoryClipFinder()
        intent = await finder.interpret_query("child marriage", conv_map)
        stories = await finder.find_stories(transcript_path, conv_map, intent)
    """

    MIN_CONVERSATION_DURATION = 90.0
    MAX_STORIES_PER_CONV = 5

    def __init__(self, client: Optional[ClaudeClient] = None):
        self.client = client or ClaudeClient()
        self._interpret_prompt = _load_prompt("query_interpret.md")
        self._story_prompt = _load_prompt("story_detection.md")
        logger.info("StoryClipFinder initialized")

    # -----------------------------------------------------------------
    # QUERY INTERPRETATION
    # -----------------------------------------------------------------

    async def interpret_query(
        self,
        raw_query: str,
        conv_map: ConversationMap,
    ) -> QueryIntent:
        """
        Parse a free-form user query into a structured QueryIntent.

        Args:
            raw_query: The user's natural language query
            conv_map: Conversation map for context

        Returns:
            Structured QueryIntent
        """
        summary = _build_conversation_summary(conv_map)
        prompt = self._interpret_prompt.replace("{{CONVERSATION_MAP}}", summary)
        prompt = prompt.replace("{{QUERY}}", raw_query)

        logger.info(f"Interpreting query: '{raw_query}'")

        try:
            response = await self.client.complete_json(
                prompt=prompt,
                max_tokens=1024,
                temperature=0.0,
            )
            data = response.extract_json()
        except Exception as e:
            logger.warning(f"Query interpretation failed: {e}, falling back to topic_search")
            return QueryIntent(
                raw_query=raw_query,
                query_type="topic_search",
                topic=raw_query,
            )

        if data is None:
            return QueryIntent(raw_query=raw_query, query_type="topic_search", topic=raw_query)

        data["raw_query"] = raw_query
        intent = QueryIntent.from_dict(data)
        logger.info(f"Interpreted as: type={intent.query_type}, topic={intent.topic}, targets={len(intent.search_targets)}")
        return intent

    # -----------------------------------------------------------------
    # PASS 0: CONVERSATION FILTERING
    # -----------------------------------------------------------------

    async def _filter_conversations(
        self,
        conv_map: ConversationMap,
        intent: Optional[QueryIntent],
    ) -> List[Conversation]:
        """Filter conversations by relevance to the query intent."""
        all_convs = [
            c for c in conv_map.conversations
            if c.duration >= self.MIN_CONVERSATION_DURATION
        ]

        if intent is None:
            return all_convs

        if intent.cross_conversation:
            if intent.topic:
                topic_lower = intent.topic.lower()
                topic_words = set(topic_lower.split())
                scored = []
                for c in all_convs:
                    hints_lower = [h.lower() for h in c.topic_hint]
                    overlap = len(topic_words & set(hints_lower))
                    scored.append((c, overlap))
                scored.sort(key=lambda x: x[1], reverse=True)
                return [c for c, _ in scored]
            return all_convs

        # Targeted conversation
        if intent.target_conversation:
            target = intent.target_conversation.lower()
            # Direct ID match
            for c in all_convs:
                if c.id.lower() == target:
                    return [c]

            # Fuzzy match on topic hints
            best_match = None
            best_score = 0
            target_words = set(re.findall(r"[a-z]+", target))
            for c in all_convs:
                hints = set(h.lower() for h in c.topic_hint)
                overlap = len(target_words & hints)
                if overlap > best_score:
                    best_score = overlap
                    best_match = c

            if best_match and best_score > 0:
                logger.info(f"Matched query target to {best_match.id} (score={best_score})")
                return [best_match]

            # LLM fallback for ambiguous matches
            summary = _build_conversation_summary(conv_map)
            prompt = (
                f"Given these conversations:\n{summary}\n\n"
                f"Which conversation best matches: \"{intent.target_conversation}\"?\n"
                f"Return ONLY the conversation ID (e.g., conv_3). If none match, return \"none\"."
            )
            try:
                resp = await self.client.complete(prompt=prompt, max_tokens=50, temperature=0.0)
                match = re.search(r"conv_\d+", resp.content)
                if match:
                    conv_id = match.group(0)
                    for c in all_convs:
                        if c.id == conv_id:
                            logger.info(f"LLM matched query target to {conv_id}")
                            return [c]
            except Exception:
                pass

        return all_convs

    # -----------------------------------------------------------------
    # PASS 1: TOPIC EXTRACTION
    # -----------------------------------------------------------------

    async def _extract_topics(
        self,
        conv: Conversation,
        transcript_text: str,
        intent: Optional[QueryIntent],
    ) -> List[Topic]:
        """Extract topics/themes from a conversation."""
        query_focus = ""
        if intent and intent.topic:
            query_focus = (
                f"\n\nFOCUS: The user is specifically interested in \"{intent.topic}\". "
                f"Prioritize moments related to this topic. Also note other strong topics."
            )
        if intent and intent.search_targets:
            targets_desc = "\n".join(
                f"- {t.label}: {t.description}" for t in intent.search_targets
            )
            query_focus += (
                f"\n\nSPECIFIC MOMENTS TO FIND:\n{targets_desc}\n"
                f"Tag any matching moments with the appropriate label."
            )

        prompt = (
            f"Analyze this conversation transcript and identify all distinct topics/themes discussed.\n"
            f"For each topic, provide the timestamp range and key quotes.\n"
            f"{query_focus}\n\n"
            f"Conversation: {conv.id} ({_format_time(conv.start_time)} - {_format_time(conv.end_time)})\n"
            f"Guests: {', '.join(conv.guest_speakers[:3])}\n\n"
            f"TRANSCRIPT:\n{transcript_text}\n\n"
            f"Return JSON array of topics:\n"
            f'[{{"name": "topic name", "start_time": "[HH:MM:SS]", "end_time": "[HH:MM:SS]", '
            f'"key_quotes": ["quote1", "quote2"], "relevance_to_query": "how this relates to the query or null"}}]'
        )

        try:
            response = await self.client.complete_json(
                prompt=prompt,
                max_tokens=4096,
                temperature=0.1,
            )
            data = response.extract_json()
        except Exception as e:
            logger.warning(f"Topic extraction failed for {conv.id}: {e}")
            return []

        if not data or not isinstance(data, list):
            return []

        topics = []
        for raw in data:
            start = _parse_timestamp(raw.get("start_time", ""))
            end = _parse_timestamp(raw.get("end_time", ""))
            if start is None or end is None:
                continue
            topics.append(Topic(
                name=raw.get("name", "Unknown"),
                start_time=start,
                end_time=end,
                key_quotes=raw.get("key_quotes", []),
                relevance_to_query=raw.get("relevance_to_query"),
            ))

        logger.info(f"  {conv.id}: extracted {len(topics)} topics")
        return topics

    # -----------------------------------------------------------------
    # PASS 2: CONNECTION DETECTION
    # -----------------------------------------------------------------

    async def _detect_connections(
        self,
        conv: Conversation,
        transcript_text: str,
        topics: List[Topic],
        intent: Optional[QueryIntent],
    ) -> List[Dict[str, Any]]:
        """Find story-worthy connections between topics in a conversation."""
        if len(topics) < 1:
            return []

        topics_json = json.dumps(
            [{"name": t.name, "start": _format_time(t.start_time),
              "end": _format_time(t.end_time), "quotes": t.key_quotes[:3]}
             for t in topics],
            indent=2,
        )

        query_section = ""
        if intent and intent.topic:
            query_section = (
                f"\n## USER'S SPECIFIC REQUEST\n"
                f"The user asked: \"{intent.raw_query}\"\n"
                f"Topic focus: {intent.topic}\n"
                f"Find connections specifically relevant to this request.\n"
            )
        if intent and intent.search_targets:
            targets_desc = "\n".join(
                f"- {t.label} ({t.role_in_story}): {t.description}"
                for t in intent.search_targets
            )
            query_section += f"\nSPECIFIC MOMENTS TO CONNECT:\n{targets_desc}\n"
        if intent and intent.assembly_instruction:
            query_section += (
                f"\nASSEMBLY INSTRUCTION: {intent.assembly_instruction}\n"
                f"Propose a story that follows this instruction.\n"
            )

        prompt = self._story_prompt.replace("{{GUEST_SPEAKERS}}", ", ".join(conv.guest_speakers[:3]))
        prompt = prompt.replace("{{DURATION}}", f"{conv.duration / 60:.0f} minutes")
        prompt = prompt.replace("{{TOPICS_JSON}}", topics_json)
        prompt = prompt.replace("{{TRANSCRIPT}}", transcript_text)
        prompt = prompt.replace("{{QUERY_SECTION}}", query_section)

        try:
            response = await self.client.complete_json(
                prompt=prompt,
                max_tokens=4096,
                temperature=0.2,
            )
            data = response.extract_json()
        except Exception as e:
            logger.warning(f"Connection detection failed for {conv.id}: {e}")
            return []

        if not data or not isinstance(data, list):
            return []

        logger.info(f"  {conv.id}: found {len(data)} story proposals")
        return data

    # -----------------------------------------------------------------
    # PASS 3: ASSEMBLY VALIDATION
    # -----------------------------------------------------------------

    async def _validate_story(
        self,
        proposal: Dict[str, Any],
        conv: Conversation,
        transcript_text: str,
        intent: Optional[QueryIntent],
        story_idx: int,
    ) -> Optional[StoryClip]:
        """Validate that a story proposal works as a standalone video."""
        segments_raw = proposal.get("segments", [])
        if len(segments_raw) < 2:
            return None

        # Parse segments
        segments: List[ClipSegment] = []
        for seg in segments_raw:
            start = _parse_timestamp(seg.get("start_time", ""))
            end = _parse_timestamp(seg.get("end_time", ""))
            if start is None or end is None:
                continue
            dur = end - start
            if dur < 5 or dur > 300:
                continue
            segments.append(ClipSegment(
                start_time=start,
                end_time=end,
                duration=round(dur, 2),
                purpose=seg.get("purpose", "evidence"),
                transcript_excerpt=seg.get("transcript_excerpt", ""),
                matches_target=seg.get("matches_target"),
            ))

        if len(segments) < 2:
            return None

        total_duration = sum(s.duration for s in segments)
        if total_duration < 30 or total_duration > 600:
            return None

        # Build segment excerpts for validation
        excerpts = []
        for i, seg in enumerate(segments):
            excerpts.append(
                f"Segment {i+1} ({seg.purpose}, {_format_time(seg.start_time)}-{_format_time(seg.end_time)}):\n"
                f"{seg.transcript_excerpt}"
            )
        excerpts_text = "\n\n".join(excerpts)

        query_context = ""
        if intent:
            query_context = f"\nThe user asked: \"{intent.raw_query}\"\n"

        prompt = (
            f"You are validating a proposed composite video clip. These segments will be played back-to-back.\n\n"
            f"Story type: {proposal.get('story_type', 'unknown')}\n"
            f"Title: {proposal.get('title', 'untitled')}\n"
            f"Narrative: {proposal.get('narrative', '')}\n"
            f"{query_context}\n"
            f"SEGMENTS:\n{excerpts_text}\n\n"
            f"QUESTIONS:\n"
            f"1. Would a viewer understand the story without external context? (yes/no)\n"
            f"2. Is the narrative compelling enough for a viral clip? (yes/no)\n"
            f"3. Do the segments flow naturally back-to-back? (yes/no)\n"
            f"4. Rate 1-10 (1=terrible, 10=perfect viral clip)\n\n"
            f'Return JSON: {{"coherent": true/false, "compelling": true/false, "flows": true/false, "score": N, "feedback": "brief explanation"}}'
        )

        try:
            response = await self.client.complete_json(
                prompt=prompt,
                max_tokens=512,
                temperature=0.0,
            )
            validation = response.extract_json()
        except Exception as e:
            logger.warning(f"Validation failed for story {story_idx}: {e}")
            validation = None

        raw_score = proposal.get("score", 5)
        if validation:
            val_score = validation.get("score", 5)
            final_score = (raw_score + val_score) / 2
            if not validation.get("coherent", True):
                final_score *= 0.6
            feedback = validation.get("feedback", "")
        else:
            final_score = raw_score * 0.8
            feedback = "validation skipped"

        if final_score < 5.0:
            logger.info(f"  Story {story_idx} rejected (score={final_score:.1f})")
            return None

        story = StoryClip(
            story_id=f"story_{conv.id}_{story_idx}",
            conversation_id=conv.id,
            guest_speakers=conv.guest_speakers[:3],
            story_type=proposal.get("story_type", "unknown"),
            title=proposal.get("title", "Untitled"),
            narrative=proposal.get("narrative", ""),
            segments=segments,
            total_duration=round(total_duration, 2),
            score=round(final_score, 1),
            reasoning=f"{proposal.get('reasoning', '')} | Validation: {feedback}",
            query_intent=intent,
            query_relevance=proposal.get("narrative", "") if intent else None,
        )

        logger.info(f"  Story {story_idx} validated: '{story.title}' (score={story.score})")
        return story

    # -----------------------------------------------------------------
    # MAIN PIPELINE
    # -----------------------------------------------------------------

    async def find_stories(
        self,
        transcript_path: str,
        conv_map: ConversationMap,
        intent: Optional[QueryIntent] = None,
        max_stories: int = 10,
    ) -> List[StoryClip]:
        """
        Run the full story detection pipeline.

        Args:
            transcript_path: Path to enhanced transcript JSON
            conv_map: Pre-computed conversation map
            intent: Optional structured query intent
            max_stories: Maximum stories to return

        Returns:
            Ranked list of validated StoryClip objects
        """
        total_start = time.time()
        logger.info("=== StoryClipFinder Pipeline Start ===")
        if intent:
            logger.info(f"Query: '{intent.raw_query}' (type={intent.query_type})")

        # Load transcript
        with open(transcript_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        utterances = data.get("utterances", [])
        logger.info(f"Loaded {len(utterances)} utterances")

        # Pass 0: Filter conversations
        logger.info("--- PASS 0: CONVERSATION FILTER ---")
        convs = await self._filter_conversations(conv_map, intent)
        logger.info(f"Processing {len(convs)} conversations")

        all_stories: List[StoryClip] = []

        for conv in convs:
            if len(all_stories) >= max_stories * 2:
                break

            transcript_text = _get_conversation_transcript(utterances, conv)
            if len(transcript_text) < 200:
                continue

            # Truncate very long conversations for Claude's context
            if len(transcript_text) > 80000:
                transcript_text = transcript_text[:80000] + "\n[... truncated ...]"

            # Pass 1: Topic extraction
            logger.info(f"--- PASS 1: TOPICS for {conv.id} ({conv.duration/60:.0f}min) ---")
            topics = await self._extract_topics(conv, transcript_text, intent)
            await asyncio.sleep(0.3)

            # Pass 2: Connection detection
            logger.info(f"--- PASS 2: CONNECTIONS for {conv.id} ---")
            proposals = await self._detect_connections(conv, transcript_text, topics, intent)
            await asyncio.sleep(0.3)

            # Pass 3: Validate each proposal
            logger.info(f"--- PASS 3: VALIDATION for {conv.id} ({len(proposals)} proposals) ---")
            for pidx, proposal in enumerate(proposals[:self.MAX_STORIES_PER_CONV]):
                story = await self._validate_story(proposal, conv, transcript_text, intent, pidx + 1)
                if story:
                    all_stories.append(story)
                await asyncio.sleep(0.2)

        # Rank by score and trim
        all_stories.sort(key=lambda s: s.score, reverse=True)
        final = all_stories[:max_stories]

        elapsed = time.time() - total_start
        logger.info(f"=== StoryClipFinder Complete: {len(final)} stories in {elapsed:.1f}s ===")
        return final

    # -----------------------------------------------------------------
    # OUTPUT
    # -----------------------------------------------------------------

    def save_results(
        self,
        stories: List[StoryClip],
        output_dir: str,
        intent: Optional[QueryIntent] = None,
    ) -> None:
        """Save story clip results to JSON and markdown report."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # JSON results
        results = {
            "total_stories": len(stories),
            "query": intent.to_dict() if intent else None,
            "stories": [s.to_dict() for s in stories],
        }
        json_path = out / "story_clips_results.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        # Markdown report
        report_lines = ["# Story Clips Report\n"]
        if intent:
            report_lines.append(f"**Query:** {intent.raw_query}\n")
            report_lines.append(f"**Type:** {intent.query_type}\n")
            if intent.topic:
                report_lines.append(f"**Topic:** {intent.topic}\n")
            report_lines.append("")

        report_lines.append(f"**Total stories found:** {len(stories)}\n")

        for i, story in enumerate(stories, 1):
            report_lines.append(f"---\n## Story {i}: {story.title}\n")
            report_lines.append(f"- **Type:** {story.story_type}")
            report_lines.append(f"- **Score:** {story.score}/10")
            report_lines.append(f"- **Conversation:** {story.conversation_id}")
            report_lines.append(f"- **Guests:** {', '.join(story.guest_speakers)}")
            report_lines.append(f"- **Total duration:** {story.total_duration:.0f}s")
            if story.query_relevance:
                report_lines.append(f"- **Query relevance:** {story.query_relevance}")
            report_lines.append(f"\n**Narrative:** {story.narrative}\n")
            report_lines.append(f"**Reasoning:** {story.reasoning}\n")
            report_lines.append("**Segments:**\n")
            for j, seg in enumerate(story.segments, 1):
                report_lines.append(
                    f"{j}. **{seg.purpose.upper()}** "
                    f"[{_format_time(seg.start_time)} - {_format_time(seg.end_time)}] "
                    f"({seg.duration:.0f}s)"
                )
                if seg.transcript_excerpt:
                    excerpt = seg.transcript_excerpt[:200]
                    report_lines.append(f"   > {excerpt}")
                if seg.matches_target:
                    report_lines.append(f"   *Matches: {seg.matches_target}*")
            report_lines.append("")

        md_path = out / "story_clips_report.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines))

        logger.info(f"Results saved to {out}")


# =============================================================================
# SYNC ENTRY POINT
# =============================================================================

def find_stories_sync(
    transcript_path: str,
    conversation_map_path: str,
    output_dir: str = "outputs/stories",
    max_stories: int = 10,
    query: Optional[str] = None,
) -> List[StoryClip]:
    """Synchronous entry point for CLI usage."""
    from src.conversation_segmenter_v3 import ConversationMap as CMap

    with open(conversation_map_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    convs = []
    for c in raw.get("conversations", []):
        convs.append(Conversation(**c))
    conv_map = CMap(
        conversations=convs,
        total_conversations=raw.get("total_conversations", len(convs)),
        total_duration=raw.get("total_duration", 0),
        source_file=raw.get("source_file", ""),
    )

    async def _run():
        finder = StoryClipFinder()
        intent = None
        if query:
            intent = await finder.interpret_query(query, conv_map)
        stories = await finder.find_stories(transcript_path, conv_map, intent, max_stories)
        finder.save_results(stories, output_dir, intent)
        return stories

    return asyncio.run(_run())
