"""
Topic Mapper - LLM-enhanced granular topic segmentation.

Breaks each conversation into named topic blocks (~15-60s each)
using Claude. Batches 3 sequential 5-min chunks per API call for
efficiency while preserving fine-grained precision.

After mapping, builds a within-conversation Topic Continuity Index
that cross-references recurring topic_ids and flags composite
clip candidates. Includes a programmatic fuzzy-match safety net
to merge near-duplicate topic_ids within each conversation.
"""

import asyncio
import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from src.anthropic_client import ClaudeClient
from src.conversation_segmenter_v3 import Conversation, ConversationMap

logger = logging.getLogger(__name__)

CHUNK_DURATION = 300  # 5-minute chunks for analysis granularity
BATCH_SIZE = 3        # chunks per API call


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class TopicBlock:
    """A single topic block within a conversation timeline."""
    topic_name: str
    topic_id: str
    start_time: float
    end_time: float
    duration: float
    key_quotes: List[str]
    speakers: List[str]
    sentiment: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ConversationTopics:
    """All topics for a single conversation."""
    conversation_id: str
    guest_speakers: List[str]
    topics: List[TopicBlock]
    topic_summary: str
    unique_topic_ids: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "guest_speakers": self.guest_speakers,
            "topics": [t.to_dict() for t in self.topics],
            "topic_summary": self.topic_summary,
            "unique_topic_ids": self.unique_topic_ids,
        }


@dataclass
class TopicOccurrence:
    """A single occurrence of a topic within a conversation."""
    start_time: float
    end_time: float
    sentiment: str
    key_quote: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TopicContinuityIndex:
    """Within-conversation cross-reference of recurring topics."""
    by_conversation: Dict[str, Dict[str, List[TopicOccurrence]]]
    recurring: Dict[str, List[str]]

    def get_recurrences(self, conv_id: str) -> Dict[str, List[TopicOccurrence]]:
        """Get only topics that appear 2+ times in a conversation."""
        conv_topics = self.by_conversation.get(conv_id, {})
        return {
            tid: occs for tid, occs in conv_topics.items()
            if len(occs) >= 2
        }

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"by_conversation": {}, "recurring": self.recurring}
        for cid, topics in self.by_conversation.items():
            result["by_conversation"][cid] = {
                tid: [o.to_dict() for o in occs]
                for tid, occs in topics.items()
            }
        return result


@dataclass
class TopicMap:
    """Full topic map for an entire stream."""
    conversations: List[ConversationTopics]
    all_topic_ids: List[str]
    total_topics: int
    source_file: str
    continuity_index: Optional[TopicContinuityIndex] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "conversations": [c.to_dict() for c in self.conversations],
            "all_topic_ids": self.all_topic_ids,
            "total_topics": self.total_topics,
            "source_file": self.source_file,
        }
        if self.continuity_index:
            result["continuity_index"] = self.continuity_index.to_dict()
        return result


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


def _get_utterances_in_range(
    utterances: List[Dict],
    indices: List[int],
    start: float,
    end: float,
) -> str:
    """Format utterances within a time range."""
    lines = []
    for idx in indices:
        if idx >= len(utterances):
            continue
        u = utterances[idx]
        if u["start"] >= start and u["start"] < end:
            ts = _format_time(u["start"])
            lines.append(f"[{ts}] {u['speaker']}: {u['text']}")
    return "\n".join(lines)


def _chunk_conversation(
    utterances: List[Dict],
    conv: Conversation,
    chunk_dur: float = CHUNK_DURATION,
) -> List[Tuple[float, float, str]]:
    """Split a conversation into time chunks with formatted text."""
    chunks = []
    start = conv.start_time
    while start < conv.end_time:
        end = min(start + chunk_dur, conv.end_time)
        text = _get_utterances_in_range(utterances, conv.utterance_indices, start, end)
        if text.strip():
            chunks.append((start, end, text))
        start = end
    return chunks


# =============================================================================
# TOPIC MAPPER
# =============================================================================

class TopicMapper:
    """
    Maps granular topics within each conversation using Claude.
    Batches 3 sequential 5-min chunks per API call for efficiency.

    Usage:
        mapper = TopicMapper()
        topic_map = await mapper.map_topics(transcript_path, conv_map)
    """

    MIN_CONVERSATION_DURATION = 60.0

    def __init__(self, client: Optional[ClaudeClient] = None):
        self.client = client or ClaudeClient()
        self._prompt_template = _load_prompt("topic_mapping.md")
        logger.info("TopicMapper initialized")

    def _batch_chunks(
        self, chunks: List[Tuple[float, float, str]]
    ) -> List[List[Tuple[float, float, str]]]:
        """Group chunks into batches of BATCH_SIZE for fewer API calls."""
        batches = []
        for i in range(0, len(chunks), BATCH_SIZE):
            batches.append(chunks[i:i + BATCH_SIZE])
        return batches

    async def _map_chunk_batch(
        self,
        conv: Conversation,
        batch: List[Tuple[float, float, str]],
        previous_topic_ids: List[str],
    ) -> List[TopicBlock]:
        """Map topics for a batch of consecutive chunks in one API call."""
        prev_section = ""
        if previous_topic_ids:
            prev_section = (
                f"Topics already seen in this conversation (reuse IDs if same subject): "
                f"{', '.join(previous_topic_ids)}"
            )

        batch_start = _format_time(batch[0][0])
        batch_end = _format_time(batch[-1][1])

        transcript_parts = []
        for chunk_start, chunk_end, chunk_text in batch:
            header = f"--- Chunk [{_format_time(chunk_start)} - {_format_time(chunk_end)}] ---"
            transcript_parts.append(f"{header}\n{chunk_text}")
        combined_transcript = "\n\n".join(transcript_parts)

        prompt = self._prompt_template
        prompt = prompt.replace("{{CONVERSATION_ID}}", conv.id)
        prompt = prompt.replace("{{GUEST_SPEAKERS}}", ", ".join(conv.guest_speakers[:4]))
        prompt = prompt.replace("{{CHUNK_START}}", batch_start)
        prompt = prompt.replace("{{CHUNK_END}}", batch_end)
        prompt = prompt.replace("{{PREVIOUS_TOPICS}}", prev_section)
        prompt = prompt.replace("{{TRANSCRIPT}}", combined_transcript)

        try:
            response = await self.client.complete_json(
                prompt=prompt,
                max_tokens=8192,
                temperature=0.1,
            )
            data = response.extract_json()
        except Exception as e:
            logger.warning(f"Topic mapping failed for {conv.id} batch {batch_start}-{batch_end}: {e}")
            return []

        if not data or not isinstance(data, list):
            return []

        blocks = []
        for raw in data:
            start = _parse_timestamp(raw.get("start_time", ""))
            end = _parse_timestamp(raw.get("end_time", ""))
            if start is None or end is None:
                continue
            dur = end - start
            if dur < 5:
                continue

            blocks.append(TopicBlock(
                topic_name=raw.get("topic_name", "Unknown"),
                topic_id=raw.get("topic_id", "unknown"),
                start_time=round(start, 2),
                end_time=round(end, 2),
                duration=round(dur, 2),
                key_quotes=raw.get("key_quotes", [])[:2],
                speakers=raw.get("speakers", []),
                sentiment=raw.get("sentiment", "calm"),
            ))

        return blocks

    async def map_conversation(
        self,
        conv: Conversation,
        utterances: List[Dict],
    ) -> ConversationTopics:
        """Map all topics in a single conversation using batched API calls."""
        chunks = _chunk_conversation(utterances, conv)
        if not chunks:
            return ConversationTopics(
                conversation_id=conv.id,
                guest_speakers=conv.guest_speakers,
                topics=[],
                topic_summary="No content",
                unique_topic_ids=[],
            )

        batches = self._batch_chunks(chunks)
        all_blocks: List[TopicBlock] = []
        seen_ids: List[str] = []

        for batch in batches:
            blocks = await self._map_chunk_batch(conv, batch, seen_ids)
            all_blocks.extend(blocks)
            for b in blocks:
                if b.topic_id not in seen_ids:
                    seen_ids.append(b.topic_id)
            await asyncio.sleep(0.3)

        all_blocks.sort(key=lambda b: b.start_time)

        # Fuzzy-merge near-duplicate topic IDs within this conversation
        all_blocks = _merge_similar_topic_ids(all_blocks)

        topic_names = list(dict.fromkeys(b.topic_name for b in all_blocks))
        summary = ", ".join(topic_names[:5])
        if len(topic_names) > 5:
            summary += f", and {len(topic_names) - 5} more"

        unique_ids = list(dict.fromkeys(b.topic_id for b in all_blocks))

        logger.info(f"  {conv.id}: {len(all_blocks)} topic blocks, {len(unique_ids)} unique topics")

        return ConversationTopics(
            conversation_id=conv.id,
            guest_speakers=conv.guest_speakers,
            topics=all_blocks,
            topic_summary=summary,
            unique_topic_ids=unique_ids,
        )

    async def map_topics(
        self,
        transcript_path: str,
        conv_map: ConversationMap,
    ) -> TopicMap:
        """
        Map topics for all conversations in a stream.

        Returns:
            TopicMap with granular topic blocks and a continuity index
        """
        logger.info("=== TopicMapper Start ===")

        with open(transcript_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        utterances = data.get("utterances", [])
        logger.info(f"Loaded {len(utterances)} utterances")

        eligible = [
            c for c in conv_map.conversations
            if c.duration >= self.MIN_CONVERSATION_DURATION
        ]
        logger.info(f"Mapping topics for {len(eligible)} conversations")

        all_conv_topics: List[ConversationTopics] = []

        for conv in eligible:
            logger.info(f"Mapping {conv.id} ({conv.duration / 60:.0f}min)...")
            ct = await self.map_conversation(conv, utterances)
            all_conv_topics.append(ct)

        all_ids: Set[str] = set()
        total = 0
        for ct in all_conv_topics:
            all_ids.update(ct.unique_topic_ids)
            total += len(ct.topics)

        continuity = build_continuity_index(all_conv_topics)

        topic_map = TopicMap(
            conversations=all_conv_topics,
            all_topic_ids=sorted(all_ids),
            total_topics=total,
            source_file=transcript_path,
            continuity_index=continuity,
        )

        recurring_count = sum(len(v) for v in continuity.recurring.values())
        logger.info(
            f"=== TopicMapper Complete: {total} blocks, {len(all_ids)} unique IDs, "
            f"{recurring_count} recurring topics ==="
        )
        return topic_map


# =============================================================================
# TOPIC DEDUP (EMBEDDING-BASED WITH WORD-OVERLAP FALLBACK)
# =============================================================================

_embedding_model = None
_embedding_available: Optional[bool] = None


def _get_embedding_model():
    """Lazy-load the sentence-transformer model. Returns None if unavailable."""
    global _embedding_model, _embedding_available
    if _embedding_available is False:
        return None
    if _embedding_model is not None:
        return _embedding_model
    try:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        _embedding_available = True
        logger.info("  Loaded sentence-transformer model for topic dedup")
        return _embedding_model
    except ImportError:
        _embedding_available = False
        logger.info("  sentence-transformers not installed, using word-overlap fallback")
        return None


def _compute_topic_similarity(
    names: List[str], ids: List[str],
) -> List[List[float]]:
    """Compute pairwise similarity matrix. Uses embeddings if available, else word overlap."""
    n = len(names)
    model = _get_embedding_model()

    if model is not None:
        embeddings = model.encode(names, convert_to_numpy=True)
        from numpy import dot
        from numpy.linalg import norm
        sim = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                cos = float(dot(embeddings[i], embeddings[j]) / (norm(embeddings[i]) * norm(embeddings[j]) + 1e-9))
                sim[i][j] = cos
                sim[j][i] = cos
        return sim

    word_sets_names = [_word_set(name) for name in names]
    word_sets_ids = [_word_set(tid) for tid in ids]
    sim = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            name_overlap = _word_overlap_sets(word_sets_names[i], word_sets_names[j])
            id_overlap = _word_overlap_sets(word_sets_ids[i], word_sets_ids[j])
            score = max(name_overlap, id_overlap)
            sim[i][j] = score
            sim[j][i] = score
    return sim


def _word_set(s: str) -> Set[str]:
    return set(re.split(r"[_\s\-]+", s.lower())) - {"", "the", "a", "an", "of", "in", "on", "and", "or"}


def _word_overlap_sets(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _merge_similar_topic_ids(
    blocks: List[TopicBlock],
    threshold: float = 0.70,
) -> List[TopicBlock]:
    """
    Merge near-duplicate topic_ids within a conversation using embeddings
    (with word-overlap fallback). Keeps the first-seen ID as canonical.
    """
    unique_ids: List[str] = []
    unique_names: List[str] = []
    id_to_idx: Dict[str, int] = {}

    for b in blocks:
        if b.topic_id not in id_to_idx:
            id_to_idx[b.topic_id] = len(unique_ids)
            unique_ids.append(b.topic_id)
            unique_names.append(b.topic_name)

    if len(unique_ids) <= 1:
        return blocks

    sim_matrix = _compute_topic_similarity(unique_names, unique_ids)

    canonical: Dict[str, str] = {}
    for i, tid in enumerate(unique_ids):
        if tid in canonical:
            continue
        canonical[tid] = tid
        for j in range(i + 1, len(unique_ids)):
            other = unique_ids[j]
            if other in canonical:
                continue
            if sim_matrix[i][j] >= threshold:
                canonical[other] = tid

    for b in blocks:
        if b.topic_id in canonical:
            b.topic_id = canonical[b.topic_id]

    merge_count = sum(1 for k, v in canonical.items() if k != v)
    if merge_count > 0:
        method = "embedding" if _embedding_available else "word-overlap"
        logger.info(f"    Merged {merge_count} duplicate topic IDs ({method})")

    return blocks


def build_continuity_index(
    all_conv_topics: List[ConversationTopics],
) -> TopicContinuityIndex:
    """
    Build a within-conversation cross-reference of recurring topics.
    For each topic_id, collect all time ranges where it appears.
    Flag topics that appear 2+ times as composite clip candidates.
    """
    by_conversation: Dict[str, Dict[str, List[TopicOccurrence]]] = {}
    recurring: Dict[str, List[str]] = {}

    for ct in all_conv_topics:
        conv_topics: Dict[str, List[TopicOccurrence]] = defaultdict(list)

        for block in ct.topics:
            quote = block.key_quotes[0] if block.key_quotes else ""
            conv_topics[block.topic_id].append(TopicOccurrence(
                start_time=block.start_time,
                end_time=block.end_time,
                sentiment=block.sentiment,
                key_quote=quote,
            ))

        by_conversation[ct.conversation_id] = dict(conv_topics)

        conv_recurring = [
            tid for tid, occs in conv_topics.items()
            if len(occs) >= 2
        ]
        if conv_recurring:
            recurring[ct.conversation_id] = conv_recurring

    return TopicContinuityIndex(
        by_conversation=by_conversation,
        recurring=recurring,
    )


def save_topic_map(topic_map: TopicMap, output_path: str) -> None:
    """Save topic map to JSON file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(topic_map.to_dict(), f, indent=2, ensure_ascii=False)
    logger.info(f"Topic map saved to {path}")


def map_topics_sync(
    transcript_path: str,
    conv_map: ConversationMap,
    output_path: Optional[str] = None,
) -> TopicMap:
    """Synchronous entry point for CLI usage."""
    async def _run():
        mapper = TopicMapper()
        topic_map = await mapper.map_topics(transcript_path, conv_map)
        if output_path:
            save_topic_map(topic_map, output_path)
        return topic_map
    return asyncio.run(_run())
