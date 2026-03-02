"""
Conversation Segmenter V3 - Programmatic conversation splitting.

Splits an enhanced transcript into per-guest conversation blocks using
dominant-speaker tracking in rolling windows. No LLM needed.
"""

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

NICK_LABEL = "nick"
MIN_CONVERSATION_DURATION = 60.0
ROLLING_WINDOW_SEC = 120.0
DOMINANCE_THRESHOLD = 3
STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "i", "you", "he", "she", "it", "we", "they", "me", "him", "her",
    "us", "them", "my", "your", "his", "its", "our", "their", "mine",
    "yours", "hers", "ours", "theirs", "this", "that", "these", "those",
    "what", "which", "who", "whom", "whose", "where", "when", "why", "how",
    "not", "no", "nor", "but", "or", "and", "if", "then", "else", "of",
    "to", "in", "on", "at", "by", "for", "with", "about", "between",
    "through", "during", "before", "after", "above", "below", "from",
    "up", "down", "out", "off", "over", "under", "again", "further",
    "so", "than", "too", "very", "just", "because", "as", "until",
    "while", "also", "into", "only", "own", "same", "other",
    "some", "such", "each", "every", "both", "few", "more", "most",
    "all", "any", "here", "there", "thing", "things", "like", "know",
    "think", "say", "said", "right", "yeah", "okay", "oh", "well",
    "gonna", "going", "really", "actually", "mean", "got", "get",
    "one", "two", "even", "still", "back", "way", "much", "many",
    "uh", "um", "uhh", "hmm", "mhm", "don", "doesn", "didn", "won",
    "wouldn", "couldn", "shouldn", "ain", "let", "something", "someone",
    "anything", "nothing", "everything", "people", "person", "make",
    "take", "come", "go", "see", "look", "want", "tell", "give",
    "use", "find", "put", "try", "ask", "work", "call", "keep",
})


@dataclass
class Conversation:
    """A conversation block between Nick and one or more guests."""
    id: str
    guest_speakers: List[str]
    start_time: float
    end_time: float
    duration: float
    nick_word_count: int
    guest_word_count: int
    turn_count: int
    topic_hint: List[str]
    utterance_indices: List[int]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ConversationMap:
    """Full conversation map for a stream."""
    conversations: List[Conversation]
    total_conversations: int
    total_duration: float
    source_file: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conversations": [c.to_dict() for c in self.conversations],
            "total_conversations": self.total_conversations,
            "total_duration": self.total_duration,
            "source_file": self.source_file,
        }


_ENTITY_PATTERNS = re.compile(
    r"\b(?:"
    r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+"  # multi-word proper nouns: "Prophet Muhammad"
    r"|[A-Z][a-z]{2,}"                   # single proper nouns: "Israel", "Quran"
    r"|(?:child\s+marriage|human\s+rights|free\s+speech|death\s+penalty"
    r"|nuclear\s+weapons?|holy\s+book|hate\s+speech|sharia\s+law"
    r"|ethnic\s+cleansing|war\s+crimes?|self\s+defense"
    r"|old\s+testament|new\s+testament)"  # known compound topics
    r")\b"
)

_ENTITY_STOPWORDS = frozenset({
    "you", "your", "yeah", "yes", "yep", "yup", "no", "nah", "not", "now",
    "what", "when", "where", "why", "who", "how", "which", "whom",
    "the", "this", "that", "these", "those", "there", "here", "then",
    "but", "and", "also", "just", "okay", "right", "well", "wait",
    "because", "literally", "actually", "basically", "obviously",
    "like", "really", "very", "sure", "great", "cool", "fine",
    "can", "did", "does", "don", "isn", "are", "was", "were", "has", "had",
    "let", "got", "get", "put", "see", "say", "said", "give", "gave",
    "hey", "dude", "bro", "man", "guys", "sir", "hold", "look",
    "they", "them", "their", "she", "her", "him", "his", "its",
    "for", "from", "with", "about", "into", "over", "after", "before",
    "every", "some", "any", "all", "most", "many", "much", "few",
    "one", "two", "three", "four", "five", "six", "been", "being",
    "will", "would", "could", "should", "might", "must",
    "even", "still", "back", "again", "already", "always", "never",
    "first", "second", "last", "next", "other", "same", "different",
    "good", "bad", "new", "old", "big", "small", "long", "little",
    "whole", "real", "true", "wrong", "own", "kind", "answer", "question",
    "thank", "thanks", "please", "sorry", "maybe", "probably", "exactly",
    "correct", "incorrect", "interesting", "important", "perfect", "simple",
    "point", "problem", "reason", "example", "fact", "case", "sense",
    "agree", "disagree", "argument", "claim", "believe", "understand",
    "read", "write", "show", "prove", "explain", "watch", "listen",
    "time", "year", "years", "day", "days", "ago", "today", "century",
    "hundred", "thousand", "million", "billion", "percent", "half",
    "epic", "based", "according", "literally", "dude",
    "have", "take", "make", "come", "want", "need", "know", "think",
    "going", "gonna", "wanna", "gotta", "trying", "saying", "talking",
    "thing", "things", "something", "anything", "nothing", "everything",
    "people", "person", "somebody", "everybody", "nobody",
})

_TOPIC_WORDS = frozenset({
    "islam", "muslim", "muslims", "quran", "hadith", "hadiths", "sunnah", "sharia",
    "christian", "christianity", "bible", "torah", "jewish", "jews", "judaism",
    "atheist", "atheism", "religion", "religious", "prophet", "prophets",
    "israel", "palestine", "palestinian", "gaza", "hamas", "zionism", "zionist",
    "iran", "iraq", "syria", "turkey", "egypt", "saudi", "arab", "arabic",
    "marriage", "divorce", "abortion", "immigration", "slavery", "genocide",
    "pedophilia", "rape", "violence", "terrorism", "terrorist", "extremism",
    "racism", "sexism", "misogyny", "homophobia", "antisemitism",
    "democracy", "communism", "capitalism", "socialism", "fascism",
    "muhammad", "jesus", "moses", "aisha", "god", "allah",
    "morality", "ethics", "philosophy", "evolution", "science",
    "war", "peace", "freedom", "sovereignty", "occupation", "colonialism",
    "feminist", "feminism", "lgbtq", "transgender", "polygamy",
    "source", "evidence", "proof", "statistic", "statistics", "fact",
})


def _extract_topic_hints(utterances: List[Dict], indices: List[int], top_n: int = 8) -> List[str]:
    """Extract meaningful topic entities and phrases from a conversation."""
    entity_freq: Counter = Counter()
    topic_word_freq: Counter = Counter()

    for idx in indices:
        if idx >= len(utterances):
            continue
        text = utterances[idx].get("text", "")

        for match in _ENTITY_PATTERNS.finditer(text):
            entity = match.group().strip().lower()
            if len(entity) > 2 and entity not in _ENTITY_STOPWORDS:
                entity_freq[entity] += 1

        for word in re.findall(r"[a-z]+", text.lower()):
            if word in _TOPIC_WORDS:
                topic_word_freq[word] += 1

    combined: Counter = Counter()
    for entity, count in entity_freq.items():
        combined[entity] += count * 2
    for word, count in topic_word_freq.items():
        if word not in combined:
            combined[word] += count

    return [term for term, _ in combined.most_common(top_n)]


def _detect_nick_alias(utterances: List[Dict]) -> Optional[str]:
    """
    Detect if a deepgram_X label is actually Nick.

    In streams where Pyannote didn't identify Nick for some utterances,
    the most prolific deepgram speaker that appears across the entire
    stream is almost always the host.
    """
    nick_count = sum(1 for u in utterances if u["speaker"] == NICK_LABEL)
    if nick_count == 0:
        return None

    dg_counts: Counter = Counter()
    for u in utterances:
        s = u["speaker"]
        if s.startswith("deepgram_"):
            dg_counts[s] += 1

    if not dg_counts:
        return None

    top_dg, top_count = dg_counts.most_common(1)[0]

    # If the top deepgram speaker has more utterances than any single guest
    # and appears in >60% of 10-minute windows, it's the host
    window_size = 600
    max_t = utterances[-1]["end"]
    windows_present = 0
    total_windows = 0
    for start in range(0, int(max_t), window_size):
        total_windows += 1
        for u in utterances:
            if u["speaker"] == top_dg and start <= u["start"] < start + window_size:
                windows_present += 1
                break

    if total_windows > 0 and (windows_present / total_windows) > 0.6:
        logger.info(f"Detected '{top_dg}' as Nick alias ({top_count} utts, present in {windows_present}/{total_windows} windows)")
        return top_dg

    return None


def _get_dominant_guest(
    utterances: List[Dict],
    center_idx: int,
    nick_labels: Set[str],
    window_sec: float = ROLLING_WINDOW_SEC,
) -> Optional[str]:
    """Find the dominant non-nick speaker in a window around an utterance."""
    center_time = utterances[center_idx]["start"]
    start_t = center_time - window_sec / 2
    end_t = center_time + window_sec / 2

    guest_counts: Counter = Counter()
    for u in utterances:
        t = u["start"]
        if start_t <= t <= end_t:
            s = u["speaker"]
            if s not in nick_labels:
                guest_counts[s] += 1

    if not guest_counts:
        return None

    top_speaker, top_count = guest_counts.most_common(1)[0]
    if top_count >= DOMINANCE_THRESHOLD:
        return top_speaker
    return None


def segment_conversations(
    transcript_path: str,
    min_duration: float = MIN_CONVERSATION_DURATION,
) -> ConversationMap:
    """
    Split an enhanced transcript into per-guest conversation blocks.

    Uses a dominant-speaker tracking approach: for each point in the
    stream, determines which guest is the primary speaker in a rolling
    window. When the dominant speaker changes, a new conversation begins.

    Args:
        transcript_path: Path to the enhanced transcript JSON
        min_duration: Minimum conversation length in seconds

    Returns:
        ConversationMap with all conversations
    """
    path = Path(transcript_path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    utterances: List[Dict] = data.get("utterances", [])
    if not utterances:
        logger.warning("No utterances found in transcript")
        return ConversationMap([], 0, 0.0, str(path))

    logger.info(f"Segmenting {len(utterances)} utterances into conversations")

    nick_alias = _detect_nick_alias(utterances)
    nick_labels = {NICK_LABEL}
    if nick_alias:
        nick_labels.add(nick_alias)

    # Compute dominant guest at each utterance
    dominant_at: List[Optional[str]] = []
    for i in range(len(utterances)):
        dominant_at.append(
            _get_dominant_guest(utterances, i, nick_labels)
        )

    # Walk through and split on dominant-speaker changes
    blocks: List[Dict[str, Any]] = []
    current_dominant: Optional[str] = None
    current_indices: List[int] = []
    current_start: float = 0.0

    for i, dom in enumerate(dominant_at):
        if dom is None:
            if current_indices:
                current_indices.append(i)
            continue

        if current_dominant is None:
            current_dominant = dom
            current_start = utterances[i]["start"]
            current_indices = [i]
        elif dom == current_dominant:
            current_indices.append(i)
        else:
            # Dominant speaker changed -- close current block
            if current_indices:
                end_t = utterances[current_indices[-1]]["end"]
                dur = end_t - current_start
                if dur >= min_duration:
                    blocks.append({
                        "dominant": current_dominant,
                        "indices": list(current_indices),
                        "start": current_start,
                        "end": end_t,
                    })
            current_dominant = dom
            current_start = utterances[i]["start"]
            current_indices = [i]

    # Flush last block
    if current_indices and current_dominant:
        end_t = utterances[current_indices[-1]]["end"]
        dur = end_t - current_start
        if dur >= min_duration:
            blocks.append({
                "dominant": current_dominant,
                "indices": list(current_indices),
                "start": current_start,
                "end": end_t,
            })

    # Merge adjacent blocks with the same dominant speaker
    merged: List[Dict[str, Any]] = []
    for block in blocks:
        if merged and merged[-1]["dominant"] == block["dominant"]:
            merged[-1]["indices"].extend(block["indices"])
            merged[-1]["end"] = block["end"]
        else:
            merged.append(block)

    # Collect all guest speakers per block (not just dominant)
    conversations: List[Conversation] = []
    for idx, block in enumerate(merged):
        indices = block["indices"]
        all_guests: Set[str] = set()
        for i in indices:
            if i < len(utterances):
                s = utterances[i]["speaker"]
                if s not in nick_labels:
                    all_guests.add(s)

        nick_wc = sum(
            utterances[i].get("word_count", 0)
            for i in indices
            if i < len(utterances) and utterances[i]["speaker"] in nick_labels
        )
        guest_wc = sum(
            utterances[i].get("word_count", 0)
            for i in indices
            if i < len(utterances) and utterances[i]["speaker"] not in nick_labels
        )
        turn_count = sum(
            1 for i in indices
            if i < len(utterances) and utterances[i]["speaker"] not in nick_labels
        )

        conv = Conversation(
            id=f"conv_{idx + 1}",
            guest_speakers=sorted(all_guests),
            start_time=round(block["start"], 2),
            end_time=round(block["end"], 2),
            duration=round(block["end"] - block["start"], 2),
            nick_word_count=nick_wc,
            guest_word_count=guest_wc,
            turn_count=turn_count,
            topic_hint=_extract_topic_hints(utterances, indices),
            utterance_indices=indices,
        )
        conversations.append(conv)

    total_dur = sum(c.duration for c in conversations)
    logger.info(
        f"Segmented into {len(conversations)} conversations "
        f"({total_dur:.0f}s / {total_dur/60:.0f}min covered)"
    )

    return ConversationMap(
        conversations=conversations,
        total_conversations=len(conversations),
        total_duration=round(total_dur, 2),
        source_file=str(path),
    )


def save_conversation_map(conv_map: ConversationMap, output_path: str) -> None:
    """Save conversation map to JSON file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(conv_map.to_dict(), f, indent=2, ensure_ascii=False)
    logger.info(f"Conversation map saved to {path}")
