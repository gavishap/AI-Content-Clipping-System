"""
Visual Change Detector - Frame Comparison with LLM Engineering

Owner: Gabriel
Status: Implemented
Version: 1.0

This module detects visual changes (people appearing/leaving) between frames
using advanced LLM engineering techniques:

1. Chain of Thought (CoT) prompting - 6-step analysis
2. Self-Consistency - 3 runs with temperature variation, majority vote
3. Multi-Pass Verification - forward, backward, holistic passes

Uses Gemini 2.5 for visual analysis (good with images).

Input: List of frame paths from visual_mapper.py
Output: visual_events.json with detected changes and confidence scores
"""

import asyncio
import base64
import json
import logging
import os
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from collections import Counter

import google.generativeai as genai

logger = logging.getLogger(__name__)

# Gemini model for visual analysis
GEMINI_MODEL = "gemini-2.0-flash"

# Self-consistency parameters
N_CONSISTENCY_RUNS = 3
CONSISTENCY_TEMPERATURES = [0.0, 0.3, 0.6]
AGREEMENT_THRESHOLD = 0.67  # 2/3 majority required


class ChangeType(Enum):
    """Types of visual changes detected."""
    NEW_PERSON = "new_person"
    PERSON_LEFT = "person_left"
    LAYOUT_CHANGE = "layout_change"
    NO_CHANGE = "no_change"
    UNCERTAIN = "uncertain"


@dataclass
class PersonDescription:
    """Description of a person in a frame."""
    description: str  # "man with dark beard wearing keffiyeh"
    position: str  # "bottom-right", "left", etc.
    visual_features: List[str] = field(default_factory=list)  # ["beard", "glasses"]
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FrameComparison:
    """Comparison between two consecutive frames."""
    frame_a_path: str
    frame_b_path: str
    timestamp_a: float
    timestamp_b: float
    change_detected: bool
    change_type: ChangeType
    person_description: Optional[PersonDescription]
    confidence: float
    reasoning: str  # Chain of thought reasoning
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_a_path": self.frame_a_path,
            "frame_b_path": self.frame_b_path,
            "timestamp_a": self.timestamp_a,
            "timestamp_b": self.timestamp_b,
            "change_detected": self.change_detected,
            "change_type": self.change_type.value,
            "person_description": self.person_description.to_dict() if self.person_description else None,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }


@dataclass
class VisualEvent:
    """A verified visual change event."""
    timestamp: float
    event_type: ChangeType
    description: str  # "Man with dark beard wearing keffiyeh appeared"
    position: str  # Where on screen
    confidence: float
    verification: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type.value,
            "description": self.description,
            "position": self.position,
            "confidence": self.confidence,
            "verification": self.verification,
        }


@dataclass
class VisualEventsResult:
    """Complete result from visual change detection."""
    events: List[VisualEvent]
    total_frames_analyzed: int
    total_comparisons: int
    total_changes: int
    uncertain_events: int
    processing_metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "events": [e.to_dict() for e in self.events],
            "total_frames_analyzed": self.total_frames_analyzed,
            "total_comparisons": self.total_comparisons,
            "total_changes": self.total_changes,
            "uncertain_events": self.uncertain_events,
            "processing_metadata": self.processing_metadata,
        }
    
    def save(self, path: str) -> None:
        """Save events to JSON file."""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Visual events saved to: {path}")
    
    @classmethod
    def load(cls, path: str) -> 'VisualEventsResult':
        """Load events from JSON file."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        events = []
        for e in data.get("events", []):
            events.append(VisualEvent(
                timestamp=e["timestamp"],
                event_type=ChangeType(e["event_type"]),
                description=e["description"],
                position=e["position"],
                confidence=e["confidence"],
                verification=e.get("verification", {}),
            ))
        
        return cls(
            events=events,
            total_frames_analyzed=data.get("total_frames_analyzed", 0),
            total_comparisons=data.get("total_comparisons", 0),
            total_changes=data.get("total_changes", 0),
            uncertain_events=data.get("uncertain_events", 0),
            processing_metadata=data.get("processing_metadata", {}),
        )


class VisualChangeDetector:
    """
    Detects visual changes between frames using LLM engineering.
    
    Uses Chain of Thought prompting, self-consistency voting,
    and multi-pass verification for high accuracy.
    
    Usage:
        detector = VisualChangeDetector()
        events = await detector.detect_changes(frame_paths, interval=30)
        events.save("visual_events.json")
    """
    
    # Chain of Thought prompt for frame comparison
    COT_PROMPT = """You are analyzing two consecutive frames from a video stream to detect if any new person appeared or if someone left.

## Instructions
Analyze the frames step by step:

STEP 1 - COUNT: How many people are visible in Frame A? In Frame B?

STEP 2 - POSITIONS: List the position of each person in both frames (left, right, center, top-left, top-right, bottom-left, bottom-right).

STEP 3 - DESCRIPTIONS: Briefly describe each person's appearance in both frames (clothing, features, accessories).

STEP 4 - COMPARE: Match people between frames. Who is the same person? Who is new? Who left?

STEP 5 - CHANGES: Based on comparison, is there a change?
- NEW_PERSON: Someone appeared who wasn't in Frame A
- PERSON_LEFT: Someone from Frame A is no longer in Frame B  
- LAYOUT_CHANGE: Same people but layout changed significantly
- NO_CHANGE: Same people, same positions

STEP 6 - CONCLUSION: What is your final determination?

## Response Format
Respond with JSON:
```json
{
    "step1_count": {"frame_a": 2, "frame_b": 3},
    "step2_positions": {
        "frame_a": ["left: person1", "right: person2"],
        "frame_b": ["left: person1", "right: person2", "bottom-right: new person"]
    },
    "step3_descriptions": {
        "frame_a": [{"position": "left", "description": "man with beard"}],
        "frame_b": [{"position": "left", "description": "man with beard"}, {"position": "bottom-right", "description": "new man with keffiyeh"}]
    },
    "step4_matching": "Person on left is same (man with beard). New person appeared bottom-right.",
    "step5_change_type": "NEW_PERSON",
    "step6_conclusion": {
        "change_detected": true,
        "change_type": "NEW_PERSON",
        "person_description": "man with dark beard wearing keffiyeh",
        "person_position": "bottom-right",
        "confidence": 0.92,
        "reasoning": "Clear new face visible in bottom-right panel that wasn't in previous frame"
    }
}
```"""

    # Verification prompts for multi-pass
    FORWARD_VERIFY_PROMPT = """Looking at Frame A (earlier) and Frame B (later), did a new person appear or did someone leave?
Focus on: What changed going FROM Frame A TO Frame B?

Respond with JSON:
{
    "change_detected": true/false,
    "change_type": "NEW_PERSON" / "PERSON_LEFT" / "NO_CHANGE",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}"""

    BACKWARD_VERIFY_PROMPT = """Looking at Frame B (later) first, then Frame A (earlier), can you identify anyone in Frame B who wasn't in Frame A?
Focus on: Looking BACK from Frame B, who is NEW compared to Frame A?

Respond with JSON:
{
    "change_detected": true/false,
    "change_type": "NEW_PERSON" / "PERSON_LEFT" / "NO_CHANGE", 
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}"""

    HOLISTIC_VERIFY_PROMPT = """Looking at both frames together as a pair, describe the overall change:
- Are there the same number of people?
- Is someone clearly new in Frame B?
- Did someone from Frame A disappear in Frame B?

Respond with JSON:
{
    "same_people_count": true/false,
    "change_detected": true/false,
    "change_type": "NEW_PERSON" / "PERSON_LEFT" / "NO_CHANGE",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize with Gemini API key.
        
        Args:
            api_key: Gemini API key (defaults to GEMINI_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Gemini API key required. Set GEMINI_API_KEY env var "
                "or pass api_key parameter."
            )
        
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(GEMINI_MODEL)
        
        logger.info(f"VisualChangeDetector initialized with Gemini model: {GEMINI_MODEL}")
    
    async def detect_changes(
        self,
        frame_paths: List[str],
        interval: int = 30,
        skip_verification: bool = False,
    ) -> VisualEventsResult:
        """
        Detect visual changes between consecutive frames.
        
        Args:
            frame_paths: Ordered list of frame image paths
            interval: Seconds between frames
            skip_verification: If True, skip multi-pass verification (faster but less accurate)
            
        Returns:
            VisualEventsResult with detected events
        """
        if len(frame_paths) < 2:
            return VisualEventsResult(
                events=[],
                total_frames_analyzed=len(frame_paths),
                total_comparisons=0,
                total_changes=0,
                uncertain_events=0,
            )
        
        logger.info(f"Analyzing {len(frame_paths)} frames for visual changes...")
        
        events: List[VisualEvent] = []
        total_comparisons = len(frame_paths) - 1
        uncertain_count = 0
        
        # Compare consecutive frame pairs
        for i in range(len(frame_paths) - 1):
            frame_a = frame_paths[i]
            frame_b = frame_paths[i + 1]
            timestamp_a = i * interval
            timestamp_b = (i + 1) * interval
            
            logger.debug(f"Comparing frames {i} and {i+1} ({timestamp_a}s - {timestamp_b}s)")
            
            try:
                # Run self-consistency detection
                comparison = await self._detect_with_consistency(
                    frame_a, frame_b, timestamp_a, timestamp_b
                )
                
                if comparison.change_detected and comparison.change_type != ChangeType.NO_CHANGE:
                    # Run multi-pass verification if enabled
                    if not skip_verification:
                        verification = await self._verify_change(
                            frame_a, frame_b, comparison
                        )
                    else:
                        verification = {
                            "skipped": True,
                            "consistency_agreement": comparison.confidence,
                        }
                    
                    # Create event if verified
                    if verification.get("verified", True) or verification.get("skipped", False):
                        event = VisualEvent(
                            timestamp=timestamp_b,  # Use the later timestamp
                            event_type=comparison.change_type,
                            description=self._build_event_description(comparison),
                            position=comparison.person_description.position if comparison.person_description else "unknown",
                            confidence=self._calibrate_confidence(
                                comparison.confidence,
                                verification,
                            ),
                            verification=verification,
                        )
                        events.append(event)
                        logger.info(
                            f"Detected {event.event_type.value} at {timestamp_b}s: "
                            f"{event.description} (confidence: {event.confidence:.2f})"
                        )
                    else:
                        uncertain_count += 1
                        logger.debug(
                            f"Change at {timestamp_b}s failed verification "
                            f"(agreement: {verification.get('pass_agreement', 'N/A')})"
                        )
                
            except Exception as e:
                logger.warning(f"Error comparing frames {i} and {i+1}: {e}")
                uncertain_count += 1
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.2)
        
        result = VisualEventsResult(
            events=events,
            total_frames_analyzed=len(frame_paths),
            total_comparisons=total_comparisons,
            total_changes=len(events),
            uncertain_events=uncertain_count,
            processing_metadata={
                "interval_seconds": interval,
                "consistency_runs": N_CONSISTENCY_RUNS,
                "verification_enabled": not skip_verification,
            },
        )
        
        logger.info(
            f"Visual change detection complete: "
            f"{len(events)} events detected, {uncertain_count} uncertain"
        )
        
        return result
    
    async def _detect_with_consistency(
        self,
        frame_a: str,
        frame_b: str,
        timestamp_a: float,
        timestamp_b: float,
    ) -> FrameComparison:
        """
        Detect change using self-consistency (multiple runs, majority vote).
        """
        results: List[Dict[str, Any]] = []
        
        # Run multiple times with different temperatures
        for run_idx, temp in enumerate(CONSISTENCY_TEMPERATURES[:N_CONSISTENCY_RUNS]):
            try:
                result = await self._run_cot_analysis(frame_a, frame_b, temperature=temp)
                results.append(result)
            except Exception as e:
                logger.warning(f"Consistency run {run_idx} failed: {e}")
        
        if not results:
            raise RuntimeError("All consistency runs failed")
        
        # Majority vote on change type
        change_types = [r.get("step6_conclusion", {}).get("change_type", "NO_CHANGE") for r in results]
        change_counter = Counter(change_types)
        winner_type, winner_count = change_counter.most_common(1)[0]
        
        agreement_ratio = winner_count / len(results)
        
        # Get the best result (one that matches winner)
        best_result = next(
            r for r in results 
            if r.get("step6_conclusion", {}).get("change_type") == winner_type
        )
        
        conclusion = best_result.get("step6_conclusion", {})
        
        # Parse change type
        try:
            change_type = ChangeType(winner_type.upper() if winner_type else "NO_CHANGE")
        except ValueError:
            change_type = ChangeType.NO_CHANGE
        
        # Build person description if applicable
        person_desc = None
        if change_type in [ChangeType.NEW_PERSON, ChangeType.PERSON_LEFT]:
            person_desc = PersonDescription(
                description=conclusion.get("person_description", "unknown"),
                position=conclusion.get("person_position", "unknown"),
                visual_features=[],
            )
        
        # Build reasoning from steps
        reasoning = self._extract_reasoning(best_result)
        
        return FrameComparison(
            frame_a_path=frame_a,
            frame_b_path=frame_b,
            timestamp_a=timestamp_a,
            timestamp_b=timestamp_b,
            change_detected=change_type not in [ChangeType.NO_CHANGE, ChangeType.UNCERTAIN],
            change_type=change_type,
            person_description=person_desc,
            confidence=agreement_ratio * conclusion.get("confidence", 0.5),
            reasoning=reasoning,
        )
    
    async def _run_cot_analysis(
        self,
        frame_a: str,
        frame_b: str,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        """Run Chain of Thought analysis on two frames."""
        # Load and encode images
        image_a = self._load_image(frame_a)
        image_b = self._load_image(frame_b)
        
        # Build prompt with images
        contents = [
            "Frame A (earlier):",
            image_a,
            "Frame B (later):",
            image_b,
            self.COT_PROMPT,
        ]
        
        # Call Gemini with specified temperature
        generation_config = genai.types.GenerationConfig(
            temperature=temperature,
            max_output_tokens=2048,
        )
        
        response = await asyncio.to_thread(
            self.model.generate_content,
            contents,
            generation_config=generation_config,
        )
        
        # Parse JSON response
        return self._parse_json_response(response.text)
    
    async def _verify_change(
        self,
        frame_a: str,
        frame_b: str,
        comparison: FrameComparison,
    ) -> Dict[str, Any]:
        """
        Run 3-pass verification on detected change.
        
        Pass 1: Forward (A -> B)
        Pass 2: Backward (B -> A perspective)
        Pass 3: Holistic (both together)
        """
        image_a = self._load_image(frame_a)
        image_b = self._load_image(frame_b)
        
        # Run all three passes concurrently
        tasks = [
            self._run_verification_pass(image_a, image_b, self.FORWARD_VERIFY_PROMPT, "forward"),
            self._run_verification_pass(image_b, image_a, self.BACKWARD_VERIFY_PROMPT, "backward"),
            self._run_verification_pass(image_a, image_b, self.HOLISTIC_VERIFY_PROMPT, "holistic"),
        ]
        
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            logger.warning(f"Verification failed: {e}")
            return {"verified": False, "error": str(e)}
        
        # Count agreements
        valid_results = []
        for r in results:
            if isinstance(r, Exception):
                logger.warning(f"Verification pass failed: {r}")
            elif isinstance(r, dict):
                valid_results.append(r)
        
        if not valid_results:
            return {"verified": False, "error": "All verification passes failed"}
        
        # Check if passes agree on change detection
        change_votes = [r.get("change_detected", False) for r in valid_results]
        agreement_ratio = sum(change_votes) / len(change_votes)
        
        # Also check change type agreement
        type_votes = [r.get("change_type", "NO_CHANGE") for r in valid_results]
        type_counter = Counter(type_votes)
        type_agreement = type_counter.most_common(1)[0][1] / len(type_votes)
        
        verified = agreement_ratio >= AGREEMENT_THRESHOLD
        
        return {
            "verified": verified,
            "pass_results": valid_results,
            "change_agreement": agreement_ratio,
            "type_agreement": type_agreement,
            "pass_agreement": f"{sum(change_votes)}/{len(change_votes)}",
            "consistency_agreement": comparison.confidence,
        }
    
    async def _run_verification_pass(
        self,
        image_first: Dict,
        image_second: Dict,
        prompt: str,
        pass_name: str,
    ) -> Dict[str, Any]:
        """Run a single verification pass."""
        contents = [
            "Frame A:",
            image_first,
            "Frame B:",
            image_second,
            prompt,
        ]
        
        generation_config = genai.types.GenerationConfig(
            temperature=0.0,
            max_output_tokens=512,
        )
        
        response = await asyncio.to_thread(
            self.model.generate_content,
            contents,
            generation_config=generation_config,
        )
        
        result = self._parse_json_response(response.text)
        result["pass_name"] = pass_name
        return result
    
    def _load_image(self, path: str) -> Dict[str, str]:
        """Load image and return Gemini-compatible format."""
        with open(path, 'rb') as f:
            image_data = f.read()
        
        return {
            "mime_type": "image/jpeg",
            "data": base64.b64encode(image_data).decode('utf-8'),
        }
    
    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """Parse JSON from Gemini response."""
        # Clean up response
        text = text.strip()
        
        # Handle markdown code blocks
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            parts = text.split("```")
            if len(parts) >= 2:
                text = parts[1].strip()
                if text.startswith(('json', 'JSON')):
                    text = text[4:].strip()
        
        # Find JSON object
        if not text.startswith('{'):
            start = text.find('{')
            end = text.rfind('}')
            if start != -1 and end != -1:
                text = text[start:end + 1]
        
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON: {e}")
            return {"error": str(e), "raw": text[:200]}
    
    def _extract_reasoning(self, cot_result: Dict[str, Any]) -> str:
        """Extract reasoning summary from Chain of Thought result."""
        parts = []
        
        if "step1_count" in cot_result:
            counts = cot_result["step1_count"]
            parts.append(f"Count: A={counts.get('frame_a', '?')}, B={counts.get('frame_b', '?')}")
        
        if "step4_matching" in cot_result:
            parts.append(f"Matching: {cot_result['step4_matching']}")
        
        if "step6_conclusion" in cot_result:
            conclusion = cot_result["step6_conclusion"]
            if "reasoning" in conclusion:
                parts.append(f"Conclusion: {conclusion['reasoning']}")
        
        return " | ".join(parts) if parts else "No reasoning captured"
    
    def _build_event_description(self, comparison: FrameComparison) -> str:
        """Build human-readable event description."""
        if comparison.change_type == ChangeType.NEW_PERSON:
            if comparison.person_description:
                return f"{comparison.person_description.description} appeared"
            return "New person appeared"
        elif comparison.change_type == ChangeType.PERSON_LEFT:
            if comparison.person_description:
                return f"{comparison.person_description.description} left"
            return "Someone left"
        elif comparison.change_type == ChangeType.LAYOUT_CHANGE:
            return "Layout changed"
        else:
            return "Unknown change"
    
    def _calibrate_confidence(
        self,
        raw_confidence: float,
        verification: Dict[str, Any],
    ) -> float:
        """Calibrate confidence based on verification results."""
        # Start with raw confidence
        calibrated = raw_confidence
        
        # Adjust based on verification
        if verification.get("verified", False):
            # Boost confidence if verification passed
            change_agreement = verification.get("change_agreement", 0.5)
            type_agreement = verification.get("type_agreement", 0.5)
            
            verification_boost = (change_agreement + type_agreement) / 2 * 0.2
            calibrated = min(1.0, calibrated + verification_boost)
        elif not verification.get("skipped", False):
            # Reduce confidence if verification failed
            calibrated = calibrated * 0.7
        
        # Apply general overconfidence correction
        calibrated = calibrated * 0.9  # LLMs tend to be ~10% overconfident
        
        return round(calibrated, 3)
    
    def detect_changes_sync(
        self,
        frame_paths: List[str],
        interval: int = 30,
        skip_verification: bool = False,
    ) -> VisualEventsResult:
        """Synchronous wrapper for detect_changes."""
        return asyncio.run(
            self.detect_changes(frame_paths, interval, skip_verification)
        )


# Utility functions

def merge_nearby_events(
    events: List[VisualEvent],
    time_threshold: float = 60.0,
) -> List[VisualEvent]:
    """
    Merge events that are close in time (likely same person).
    
    Args:
        events: List of visual events
        time_threshold: Maximum seconds between events to merge
        
    Returns:
        Merged list of events
    """
    if not events:
        return []
    
    # Sort by timestamp
    sorted_events = sorted(events, key=lambda e: e.timestamp)
    
    merged: List[VisualEvent] = [sorted_events[0]]
    
    for event in sorted_events[1:]:
        last = merged[-1]
        
        # Check if should merge
        if (
            event.event_type == last.event_type and
            event.timestamp - last.timestamp <= time_threshold and
            _descriptions_similar(event.description, last.description)
        ):
            # Merge: keep earlier timestamp, update confidence
            merged_confidence = max(last.confidence, event.confidence)
            merged[-1] = VisualEvent(
                timestamp=last.timestamp,
                event_type=last.event_type,
                description=last.description,
                position=last.position,
                confidence=merged_confidence,
                verification={
                    **last.verification,
                    "merged_events": last.verification.get("merged_events", 1) + 1,
                },
            )
        else:
            merged.append(event)
    
    return merged


def _descriptions_similar(desc1: str, desc2: str) -> bool:
    """Check if two descriptions likely refer to the same person."""
    d1_lower = desc1.lower()
    d2_lower = desc2.lower()
    
    # Simple keyword overlap check
    words1 = set(d1_lower.split())
    words2 = set(d2_lower.split())
    
    overlap = len(words1 & words2)
    min_words = min(len(words1), len(words2))
    
    if min_words == 0:
        return False
    
    return overlap / min_words >= 0.5


def filter_by_confidence(
    events: List[VisualEvent],
    min_confidence: float = 0.6,
) -> List[VisualEvent]:
    """Filter events by minimum confidence threshold."""
    return [e for e in events if e.confidence >= min_confidence]
