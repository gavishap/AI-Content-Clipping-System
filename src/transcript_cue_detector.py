"""
Transcript Cue Detector - Pattern Matching + LLM Context Validation

Owner: Gabriel
Status: Implemented
Version: 1.0

This module detects intro/exit cues in transcripts using:
1. Regex pattern matching for common greetings and farewells
2. LLM context validation to filter false positives
3. Semantic similarity for greeting variations

Detects:
- Guest introductions ("Hey, thanks for having me", "What's up")
- Guest exits ("Goodbye", "Thanks for the conversation", "Take care")
- Host welcomes ("Welcome to the show", "Thanks for joining")

Input: Transcript data with words and timestamps
Output: transcript_cues.json with validated cues
"""

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Pattern, Tuple

logger = logging.getLogger(__name__)


class CueType(Enum):
    """Types of transcript cues."""
    INTRO = "intro"           # Guest joining
    EXIT = "exit"             # Guest leaving
    WELCOME = "welcome"       # Host welcoming someone
    FAREWELL = "farewell"     # Host saying goodbye
    FALSE_POSITIVE = "false_positive"


@dataclass
class PatternMatch:
    """A raw pattern match before validation."""
    timestamp: float
    end_timestamp: float
    phrase: str
    pattern_name: str
    cue_type: CueType
    word_indices: Tuple[int, int]  # (start_idx, end_idx)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "end_timestamp": self.end_timestamp,
            "phrase": self.phrase,
            "pattern_name": self.pattern_name,
            "cue_type": self.cue_type.value,
            "word_indices": list(self.word_indices),
        }


@dataclass
class TranscriptCue:
    """A detected transcript cue with context."""
    timestamp: float
    end_timestamp: float
    cue_type: CueType
    phrase: str
    speaker_id: Optional[str]
    context_before: str
    context_after: str
    confidence: float
    pattern_matched: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "end_timestamp": self.end_timestamp,
            "cue_type": self.cue_type.value,
            "phrase": self.phrase,
            "speaker_id": self.speaker_id,
            "context_before": self.context_before,
            "context_after": self.context_after,
            "confidence": self.confidence,
            "pattern_matched": self.pattern_matched,
        }


@dataclass
class ValidatedCue:
    """A cue validated with LLM context analysis."""
    cue: TranscriptCue
    is_genuine: bool
    validation_reasoning: str
    speaker_change_detected: bool
    new_speaker_description: Optional[str]
    final_confidence: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "cue": self.cue.to_dict(),
            "is_genuine": self.is_genuine,
            "validation_reasoning": self.validation_reasoning,
            "speaker_change_detected": self.speaker_change_detected,
            "new_speaker_description": self.new_speaker_description,
            "final_confidence": self.final_confidence,
        }


@dataclass
class TranscriptCuesResult:
    """Complete result from transcript cue detection."""
    raw_matches: List[PatternMatch]
    cues: List[TranscriptCue]
    validated_cues: List[ValidatedCue]
    total_intros: int
    total_exits: int
    processing_metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_matches": [m.to_dict() for m in self.raw_matches],
            "cues": [c.to_dict() for c in self.cues],
            "validated_cues": [v.to_dict() for v in self.validated_cues],
            "total_intros": self.total_intros,
            "total_exits": self.total_exits,
            "processing_metadata": self.processing_metadata,
        }
    
    def save(self, path: str) -> None:
        """Save cues to JSON file."""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Transcript cues saved to: {path}")
    
    @classmethod
    def load(cls, path: str) -> 'TranscriptCuesResult':
        """Load cues from JSON file."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        raw_matches = []
        for m in data.get("raw_matches", []):
            raw_matches.append(PatternMatch(
                timestamp=m["timestamp"],
                end_timestamp=m["end_timestamp"],
                phrase=m["phrase"],
                pattern_name=m["pattern_name"],
                cue_type=CueType(m["cue_type"]),
                word_indices=tuple(m["word_indices"]),
            ))
        
        cues = []
        for c in data.get("cues", []):
            cues.append(TranscriptCue(
                timestamp=c["timestamp"],
                end_timestamp=c["end_timestamp"],
                cue_type=CueType(c["cue_type"]),
                phrase=c["phrase"],
                speaker_id=c.get("speaker_id"),
                context_before=c.get("context_before", ""),
                context_after=c.get("context_after", ""),
                confidence=c.get("confidence", 0.7),
                pattern_matched=c.get("pattern_matched", ""),
            ))
        
        validated_cues = []
        for v in data.get("validated_cues", []):
            cue_data = v["cue"]
            validated_cues.append(ValidatedCue(
                cue=TranscriptCue(
                    timestamp=cue_data["timestamp"],
                    end_timestamp=cue_data["end_timestamp"],
                    cue_type=CueType(cue_data["cue_type"]),
                    phrase=cue_data["phrase"],
                    speaker_id=cue_data.get("speaker_id"),
                    context_before=cue_data.get("context_before", ""),
                    context_after=cue_data.get("context_after", ""),
                    confidence=cue_data.get("confidence", 0.7),
                    pattern_matched=cue_data.get("pattern_matched", ""),
                ),
                is_genuine=v["is_genuine"],
                validation_reasoning=v["validation_reasoning"],
                speaker_change_detected=v["speaker_change_detected"],
                new_speaker_description=v.get("new_speaker_description"),
                final_confidence=v["final_confidence"],
            ))
        
        return cls(
            raw_matches=raw_matches,
            cues=cues,
            validated_cues=validated_cues,
            total_intros=data.get("total_intros", 0),
            total_exits=data.get("total_exits", 0),
            processing_metadata=data.get("processing_metadata", {}),
        )


# =============================================================================
# Pattern Definitions
# =============================================================================

# Intro patterns - guest joining
INTRO_PATTERNS = {
    # Casual greetings
    "whats_up": r"\bwhat'?s?\s+up\b",
    "hey_greeting": r"\bhey\b(?:\s+(?:man|guys?|everyone|there|what'?s?\s+up))?",
    "hi_greeting": r"\bhi\b(?:\s+(?:everyone|guys?|there))?",
    "yo_greeting": r"\byo\b",
    "sup_greeting": r"\b(?:sup|wassup|whassup)\b",
    
    # Formal greetings
    "hello_greeting": r"\bhello\b(?:\s+(?:everyone|there))?",
    "good_to_be_here": r"\b(?:good|great|nice)\s+to\s+be\s+here\b",
    "thanks_for_having": r"\bthanks?\s+(?:for\s+)?having\s+me\b",
    "appreciate_having": r"\bappreciate\s+(?:you\s+)?having\s+me\b",
    "glad_to_be": r"\bglad\s+to\s+be\s+(?:here|on)\b",
    
    # Self-introduction
    "my_name_is": r"\bmy\s+name\s+(?:is|'s)\b",
    "im_here_to": r"\bi'?m\s+here\s+to\b",
    "introduce_myself": r"\blet\s+me\s+introduce\s+myself\b",
    
    # Response to welcome
    "thanks_nick": r"\bthanks?\s+(?:nick|bro|man|dude)\b",
    "pleasure": r"\b(?:pleasure|honor)\s+(?:to\s+be\s+here|is\s+mine)\b",
}

# Exit patterns - guest leaving
EXIT_PATTERNS = {
    # Goodbyes
    "goodbye": r"\bgood\s*bye\b",
    "bye_bye": r"\bbye\s*bye?\b",
    "see_you": r"\bsee\s+(?:you|ya)\s*(?:later|next\s+time|around)?\b",
    "take_care": r"\btake\s+care\b",
    "peace_out": r"\bpeace\s*(?:out)?\b",
    "later_greeting": r"\blater\b(?:\s+(?:man|guys?|everyone))?",
    
    # Thanks for conversation
    "thanks_conversation": r"\bthanks?\s+(?:for\s+)?(?:the\s+)?(?:conversation|chat|talk|debate)\b",
    "good_talking": r"\b(?:good|great|nice)\s+(?:talking|chatting)\s+(?:to|with)\s+you\b",
    "enjoyed_this": r"\benjoyed\s+(?:this|the\s+(?:conversation|debate))\b",
    
    # Exit signals
    "gotta_go": r"\b(?:gotta|got\s+to|have\s+to)\s+go\b",
    "heading_out": r"\b(?:heading|gonna\s+head)\s+out\b",
    "signing_off": r"\bsigning\s+off\b",
}

# Host welcome patterns
WELCOME_PATTERNS = {
    "welcome_show": r"\bwelcome\s+(?:to\s+)?(?:the\s+)?(?:show|stream|channel)\b",
    "thanks_joining": r"\bthanks?\s+(?:for\s+)?(?:joining|coming)\b",
    "glad_have_you": r"\b(?:glad|great|nice)\s+(?:to\s+)?have\s+you\b",
    "introduce_yourself": r"\bintroduce\s+yourself\b",
    "tell_us": r"\btell\s+us\s+(?:about|who)\b",
    "who_are_you": r"\bwho\s+are\s+you\b",
}

# Host farewell patterns
FAREWELL_PATTERNS = {
    "thanks_coming": r"\bthanks?\s+(?:for\s+)?(?:coming|being\s+here)\b",
    "good_having": r"\b(?:good|great)\s+having\s+you\b",
    "come_back": r"\bcome\s+back\s+(?:anytime|soon)\b",
    "next_guest": r"\bnext\s+(?:guest|person|caller)\b",
}


class TranscriptCueDetector:
    """
    Detects intro/exit cues in transcripts.
    
    Uses pattern matching followed by optional LLM validation
    to filter false positives.
    
    Usage:
        detector = TranscriptCueDetector()
        result = await detector.detect_cues(
            transcript_data=transcript,
            validate_with_llm=True,
        )
        result.save("transcript_cues.json")
    """
    
    def __init__(
        self,
        anthropic_client: Optional['ClaudeClient'] = None,
        custom_intro_patterns: Optional[Dict[str, str]] = None,
        custom_exit_patterns: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize detector.
        
        Args:
            anthropic_client: Optional ClaudeClient for LLM validation
            custom_intro_patterns: Additional intro patterns to match
            custom_exit_patterns: Additional exit patterns to match
        """
        self.anthropic_client = anthropic_client
        
        # Build pattern dicts
        self.intro_patterns = {**INTRO_PATTERNS}
        if custom_intro_patterns:
            self.intro_patterns.update(custom_intro_patterns)
        
        self.exit_patterns = {**EXIT_PATTERNS}
        if custom_exit_patterns:
            self.exit_patterns.update(custom_exit_patterns)
        
        self.welcome_patterns = WELCOME_PATTERNS.copy()
        self.farewell_patterns = FAREWELL_PATTERNS.copy()
        
        # Compile all patterns
        self._compiled_patterns: Dict[str, Tuple[Pattern, CueType]] = {}
        self._compile_patterns()
        
        logger.info(
            f"TranscriptCueDetector initialized with "
            f"{len(self.intro_patterns)} intro, {len(self.exit_patterns)} exit patterns"
        )
    
    def _compile_patterns(self) -> None:
        """Compile all regex patterns."""
        for name, pattern in self.intro_patterns.items():
            self._compiled_patterns[f"intro_{name}"] = (
                re.compile(pattern, re.IGNORECASE),
                CueType.INTRO,
            )
        
        for name, pattern in self.exit_patterns.items():
            self._compiled_patterns[f"exit_{name}"] = (
                re.compile(pattern, re.IGNORECASE),
                CueType.EXIT,
            )
        
        for name, pattern in self.welcome_patterns.items():
            self._compiled_patterns[f"welcome_{name}"] = (
                re.compile(pattern, re.IGNORECASE),
                CueType.WELCOME,
            )
        
        for name, pattern in self.farewell_patterns.items():
            self._compiled_patterns[f"farewell_{name}"] = (
                re.compile(pattern, re.IGNORECASE),
                CueType.FAREWELL,
            )
    
    async def detect_cues(
        self,
        transcript_data: Dict[str, Any],
        validate_with_llm: bool = True,
        context_window: int = 30,  # words of context
        min_confidence: float = 0.5,
    ) -> TranscriptCuesResult:
        """
        Detect intro/exit cues in transcript.
        
        Args:
            transcript_data: Deepgram transcript with words
            validate_with_llm: Whether to validate with LLM
            context_window: Words of context to include
            min_confidence: Minimum confidence to include
            
        Returns:
            TranscriptCuesResult with all detected cues
        """
        logger.info("Detecting transcript cues...")
        
        # Extract words
        words = self._extract_words(transcript_data)
        if not words:
            logger.warning("No words found in transcript")
            return TranscriptCuesResult(
                raw_matches=[],
                cues=[],
                validated_cues=[],
                total_intros=0,
                total_exits=0,
            )
        
        # Build full text for pattern matching
        full_text = " ".join(
            w.get("word", w.get("punctuated_word", "")) for w in words
        )
        
        # Find all pattern matches
        raw_matches = self._find_pattern_matches(words, full_text)
        logger.info(f"Found {len(raw_matches)} raw pattern matches")
        
        # Build cues with context
        cues = []
        for match in raw_matches:
            cue = self._build_cue_with_context(match, words, context_window)
            if cue.confidence >= min_confidence:
                cues.append(cue)
        
        # Filter duplicates (same timestamp, similar phrase)
        cues = self._deduplicate_cues(cues)
        logger.info(f"After deduplication: {len(cues)} cues")
        
        # Validate with LLM if enabled
        validated_cues = []
        if validate_with_llm and self.anthropic_client and cues:
            validated_cues = await self._validate_cues_with_llm(cues)
            # Filter to genuine cues only
            cues = [v.cue for v in validated_cues if v.is_genuine]
        
        # Count intro/exit types
        total_intros = sum(1 for c in cues if c.cue_type in [CueType.INTRO, CueType.WELCOME])
        total_exits = sum(1 for c in cues if c.cue_type in [CueType.EXIT, CueType.FAREWELL])
        
        result = TranscriptCuesResult(
            raw_matches=raw_matches,
            cues=cues,
            validated_cues=validated_cues,
            total_intros=total_intros,
            total_exits=total_exits,
            processing_metadata={
                "total_words": len(words),
                "patterns_used": len(self._compiled_patterns),
                "llm_validation": validate_with_llm,
                "context_window": context_window,
            },
        )
        
        logger.info(
            f"Cue detection complete: {total_intros} intros, {total_exits} exits"
        )
        
        return result
    
    def _extract_words(self, transcript_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract words from various transcript formats."""
        # Try direct words array
        if "words" in transcript_data:
            return transcript_data["words"]
        
        # Try Deepgram results format
        if "results" in transcript_data:
            channels = transcript_data["results"].get("channels", [])
            if channels:
                alternatives = channels[0].get("alternatives", [])
                if alternatives:
                    return alternatives[0].get("words", [])
        
        # Try utterances format
        if "utterances" in transcript_data:
            words = []
            for utt in transcript_data["utterances"]:
                for word in utt.get("words", []):
                    word["speaker"] = utt.get("speaker", 0)
                    words.append(word)
            return words
        
        return []
    
    def _find_pattern_matches(
        self,
        words: List[Dict[str, Any]],
        full_text: str,
    ) -> List[PatternMatch]:
        """Find all pattern matches in the text."""
        matches = []
        
        # Build word index mapping
        word_positions = self._build_word_positions(words)
        
        for pattern_name, (pattern, cue_type) in self._compiled_patterns.items():
            for match in pattern.finditer(full_text):
                # Find corresponding word indices
                start_char = match.start()
                end_char = match.end()
                
                start_word_idx, end_word_idx = self._char_to_word_indices(
                    start_char, end_char, word_positions
                )
                
                if start_word_idx is not None and start_word_idx < len(words):
                    timestamp = words[start_word_idx].get("start", 0)
                    end_timestamp = words[min(end_word_idx, len(words) - 1)].get("end", timestamp)
                    
                    matches.append(PatternMatch(
                        timestamp=timestamp,
                        end_timestamp=end_timestamp,
                        phrase=match.group(),
                        pattern_name=pattern_name,
                        cue_type=cue_type,
                        word_indices=(start_word_idx, end_word_idx),
                    ))
        
        # Sort by timestamp
        matches.sort(key=lambda m: m.timestamp)
        
        return matches
    
    def _build_word_positions(
        self,
        words: List[Dict[str, Any]],
    ) -> List[Tuple[int, int]]:
        """Build character position mapping for words."""
        positions = []
        current_pos = 0
        
        for word in words:
            text = word.get("word", word.get("punctuated_word", ""))
            start = current_pos
            end = current_pos + len(text)
            positions.append((start, end))
            current_pos = end + 1  # +1 for space
        
        return positions
    
    def _char_to_word_indices(
        self,
        start_char: int,
        end_char: int,
        word_positions: List[Tuple[int, int]],
    ) -> Tuple[Optional[int], int]:
        """Convert character positions to word indices."""
        start_word = None
        end_word = 0
        
        for i, (w_start, w_end) in enumerate(word_positions):
            if start_word is None and w_start <= start_char < w_end + 1:
                start_word = i
            if w_start < end_char:
                end_word = i
        
        return start_word, end_word
    
    def _build_cue_with_context(
        self,
        match: PatternMatch,
        words: List[Dict[str, Any]],
        context_window: int,
    ) -> TranscriptCue:
        """Build a cue with surrounding context."""
        start_idx, end_idx = match.word_indices
        
        # Get context before
        context_start = max(0, start_idx - context_window)
        context_before_words = words[context_start:start_idx]
        context_before = " ".join(
            w.get("word", w.get("punctuated_word", ""))
            for w in context_before_words
        )
        
        # Get context after
        context_end = min(len(words), end_idx + context_window + 1)
        context_after_words = words[end_idx + 1:context_end]
        context_after = " ".join(
            w.get("word", w.get("punctuated_word", ""))
            for w in context_after_words
        )
        
        # Get speaker ID from the matched words
        speaker_id = None
        if start_idx < len(words):
            speaker_id = str(words[start_idx].get("speaker", 0))
        
        # Calculate base confidence
        confidence = self._calculate_confidence(match, context_before, context_after)
        
        return TranscriptCue(
            timestamp=match.timestamp,
            end_timestamp=match.end_timestamp,
            cue_type=match.cue_type,
            phrase=match.phrase,
            speaker_id=speaker_id,
            context_before=context_before,
            context_after=context_after,
            confidence=confidence,
            pattern_matched=match.pattern_name,
        )
    
    def _calculate_confidence(
        self,
        match: PatternMatch,
        context_before: str,
        context_after: str,
    ) -> float:
        """Calculate confidence based on match and context."""
        # Base confidence by pattern type
        base_confidence = {
            "thanks_for_having": 0.9,
            "good_to_be_here": 0.9,
            "goodbye": 0.85,
            "see_you": 0.8,
            "thanks_conversation": 0.85,
            "welcome_show": 0.9,
            "thanks_joining": 0.85,
        }
        
        confidence = base_confidence.get(
            match.pattern_name.split("_", 1)[-1] if "_" in match.pattern_name else match.pattern_name,
            0.7
        )
        
        # Boost if longer phrase
        if len(match.phrase.split()) >= 3:
            confidence = min(1.0, confidence + 0.1)
        
        # Reduce for very common words that might be false positives
        common_false_positives = ["hey", "hi", "yo", "bye", "later"]
        if match.phrase.lower().strip() in common_false_positives:
            confidence *= 0.7
        
        return round(confidence, 3)
    
    def _deduplicate_cues(
        self,
        cues: List[TranscriptCue],
        time_threshold: float = 5.0,
    ) -> List[TranscriptCue]:
        """Remove duplicate cues that are too close together."""
        if not cues:
            return []
        
        # Sort by timestamp
        sorted_cues = sorted(cues, key=lambda c: c.timestamp)
        
        deduped = [sorted_cues[0]]
        
        for cue in sorted_cues[1:]:
            last = deduped[-1]
            
            # Check if too close and same type
            if (
                abs(cue.timestamp - last.timestamp) < time_threshold
                and cue.cue_type == last.cue_type
            ):
                # Keep the higher confidence one
                if cue.confidence > last.confidence:
                    deduped[-1] = cue
            else:
                deduped.append(cue)
        
        return deduped
    
    async def _validate_cues_with_llm(
        self,
        cues: List[TranscriptCue],
    ) -> List[ValidatedCue]:
        """Validate cues using LLM context analysis."""
        if not self.anthropic_client:
            return []
        
        validated = []
        
        for cue in cues:
            try:
                validation = await self._validate_single_cue(cue)
                validated.append(validation)
            except Exception as e:
                logger.warning(f"LLM validation failed for cue at {cue.timestamp}: {e}")
                # Keep cue with reduced confidence
                validated.append(ValidatedCue(
                    cue=cue,
                    is_genuine=True,  # Assume genuine if validation fails
                    validation_reasoning="LLM validation failed, kept with reduced confidence",
                    speaker_change_detected=False,
                    new_speaker_description=None,
                    final_confidence=cue.confidence * 0.7,
                ))
        
        return validated
    
    async def _validate_single_cue(self, cue: TranscriptCue) -> ValidatedCue:
        """Validate a single cue with LLM."""
        prompt = f"""Analyze if this is a genuine greeting/introduction or exit/goodbye in a livestream context.

DETECTED PHRASE: "{cue.phrase}"
DETECTED TYPE: {cue.cue_type.value}
TIMESTAMP: {cue.timestamp:.1f}s

CONTEXT BEFORE (what was said before):
"{cue.context_before}"

PHRASE IN CONTEXT:
"...{cue.context_before[-100:]} ***{cue.phrase}*** {cue.context_after[:100]}..."

CONTEXT AFTER (what was said after):
"{cue.context_after}"

Determine:
1. Is this a genuine {cue.cue_type.value.upper()}? (someone actually joining/leaving the conversation)
2. Or is this just casual speech / false positive? (greeting in middle of conversation, rhetorical, etc.)

Consider:
- Is there a speaker change around this point?
- Does the context suggest someone new is being welcomed?
- Is someone clearly saying goodbye and leaving?
- Could this be sarcasm, quoting someone, or rhetorical?
- Is this at a natural break point in the conversation?

Respond with JSON:
{{
    "cue_type": "INTRO" | "EXIT" | "WELCOME" | "FAREWELL" | "FALSE_POSITIVE",
    "is_genuine": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "explanation",
    "speaker_change_detected": true/false,
    "new_speaker_description": "if intro, describe who seems to be joining (or null)"
}}"""
        
        response = await self.anthropic_client.complete_json(prompt)
        result = response.extract_json()
        
        if result:
            is_genuine = result.get("is_genuine", True)
            detected_type = result.get("cue_type", cue.cue_type.value).upper()
            
            # Update cue type if LLM says different
            if detected_type == "FALSE_POSITIVE":
                is_genuine = False
            
            return ValidatedCue(
                cue=cue,
                is_genuine=is_genuine,
                validation_reasoning=result.get("reasoning", ""),
                speaker_change_detected=result.get("speaker_change_detected", False),
                new_speaker_description=result.get("new_speaker_description"),
                final_confidence=result.get("confidence", cue.confidence) if is_genuine else 0.0,
            )
        
        # Fallback if parsing fails
        return ValidatedCue(
            cue=cue,
            is_genuine=True,
            validation_reasoning="LLM response parsing failed",
            speaker_change_detected=False,
            new_speaker_description=None,
            final_confidence=cue.confidence * 0.8,
        )
    
    def detect_cues_sync(
        self,
        transcript_data: Dict[str, Any],
        validate_with_llm: bool = True,
        context_window: int = 30,
        min_confidence: float = 0.5,
    ) -> TranscriptCuesResult:
        """Synchronous wrapper for detect_cues."""
        return asyncio.run(
            self.detect_cues(
                transcript_data,
                validate_with_llm,
                context_window,
                min_confidence,
            )
        )


# =============================================================================
# Utility Functions
# =============================================================================

def get_intro_cues(
    result: TranscriptCuesResult,
    min_confidence: float = 0.6,
) -> List[TranscriptCue]:
    """Get intro cues above confidence threshold."""
    return [
        c for c in result.cues
        if c.cue_type in [CueType.INTRO, CueType.WELCOME]
        and c.confidence >= min_confidence
    ]


def get_exit_cues(
    result: TranscriptCuesResult,
    min_confidence: float = 0.6,
) -> List[TranscriptCue]:
    """Get exit cues above confidence threshold."""
    return [
        c for c in result.cues
        if c.cue_type in [CueType.EXIT, CueType.FAREWELL]
        and c.confidence >= min_confidence
    ]


def get_cues_in_range(
    result: TranscriptCuesResult,
    start_time: float,
    end_time: float,
) -> List[TranscriptCue]:
    """Get all cues within a time range."""
    return [
        c for c in result.cues
        if start_time <= c.timestamp <= end_time
    ]


def find_nearest_intro(
    result: TranscriptCuesResult,
    timestamp: float,
    max_distance: float = 60.0,
) -> Optional[TranscriptCue]:
    """Find the nearest intro cue to a timestamp."""
    intros = get_intro_cues(result)
    
    nearest = None
    min_distance = float('inf')
    
    for cue in intros:
        distance = abs(cue.timestamp - timestamp)
        if distance < min_distance and distance <= max_distance:
            min_distance = distance
            nearest = cue
    
    return nearest


def correlate_with_voice_events(
    cues_result: TranscriptCuesResult,
    voice_events: List[Dict[str, Any]],
    correlation_window: float = 30.0,
) -> List[Dict[str, Any]]:
    """
    Correlate transcript cues with voice events.
    
    Returns list of correlations with both cue and voice event info.
    """
    correlations = []
    
    for cue in cues_result.cues:
        if cue.cue_type not in [CueType.INTRO, CueType.WELCOME]:
            continue
        
        # Find voice events near this cue
        nearby_voice = [
            v for v in voice_events
            if abs(v.get("timestamp", 0) - cue.timestamp) <= correlation_window
        ]
        
        if nearby_voice:
            # Find closest
            closest = min(
                nearby_voice,
                key=lambda v: abs(v.get("timestamp", 0) - cue.timestamp)
            )
            
            correlations.append({
                "cue_timestamp": cue.timestamp,
                "cue_phrase": cue.phrase,
                "cue_type": cue.cue_type.value,
                "voice_timestamp": closest.get("timestamp"),
                "voice_speaker_id": closest.get("speaker_id"),
                "time_difference": abs(closest.get("timestamp", 0) - cue.timestamp),
                "correlation_strength": 1.0 - (abs(closest.get("timestamp", 0) - cue.timestamp) / correlation_window),
            })
    
    return correlations
