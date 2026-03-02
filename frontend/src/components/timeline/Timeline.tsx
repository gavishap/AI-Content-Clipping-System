"use client";

import { useEffect, useRef, useMemo } from "react";
import { useAppStore } from "@/lib/store";
import { conversationMap, topicMap, clipsResults } from "@/lib/data";
import { stringToColor, getTopicColor } from "@/lib/colors";
import { 
  Tooltip, 
  TooltipContent, 
  TooltipProvider, 
  TooltipTrigger 
} from "@/components/ui/tooltip";
import { Badge } from "@/components/ui/badge";

const TRACK_HEIGHT = 120;
const CONV_HEIGHT = 30;
const TOPIC_HEIGHT = 20;
const CLIP_HEIGHT = 15;
const RULER_HEIGHT = 20;

export function Timeline() {
  const containerRef = useRef<HTMLDivElement>(null);
  const { 
    currentTime, 
    duration, 
    zoomLevel, 
    setCurrentTime,
    selectedClipId,
    selectClip
  } = useAppStore();

  const totalWidth = duration * zoomLevel;

  // Sync scroll on mount or when playhead moves (optional auto-scroll)
  // For now, let's just allow manual scrolling + click to seek
  
  const handleTimelineClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const scrollLeft = containerRef.current.scrollLeft;
    const x = e.clientX - rect.left + scrollLeft;
    const time = Math.max(0, Math.min(x / zoomLevel, duration));
    setCurrentTime(time);
  };

  // Memoize flat lists for rendering
  const flatTopics = useMemo(() => 
    topicMap.conversations.flatMap(c => c.topics), 
  []);

  return (
    <div className="w-full h-full flex flex-col bg-background border-t border-border">
      {/* Timeline Controls / Ruler (simple) */}
      <div className="h-8 border-b border-border flex items-center px-4 justify-between bg-muted/30">
        <span className="text-xs text-muted-foreground">Timeline</span>
        <div className="text-xs font-mono">
            Scale: {zoomLevel.toFixed(1)}px/s
        </div>
      </div>

      {/* Scrollable Area */}
      <div 
        ref={containerRef}
        className="flex-1 overflow-x-auto overflow-y-hidden relative select-none"
        onClick={handleTimelineClick}
      >
        <div 
            style={{ width: `${totalWidth}px`, height: '100%', minHeight: `${TRACK_HEIGHT}px` }} 
            className="relative bg-muted/10"
        >
            {/* 1. Conversations Row */}
            {conversationMap.conversations.map((conv) => (
                <TooltipProvider key={conv.id}>
                <Tooltip>
                    <TooltipTrigger asChild>
                    <div
                        className="absolute top-0 border-r border-background/20 overflow-hidden text-[10px] px-1 whitespace-nowrap text-white/90 hover:brightness-110 cursor-pointer transition-all"
                        style={{
                            left: `${conv.start_time * zoomLevel}px`,
                            width: `${conv.duration * zoomLevel}px`,
                            height: `${CONV_HEIGHT}px`,
                            backgroundColor: stringToColor(conv.guest_speakers[0] || "unknown"),
                        }}
                    >
                        {conv.guest_speakers.join(", ")}
                    </div>
                    </TooltipTrigger>
                    <TooltipContent>
                        <p className="font-bold">{conv.id}</p>
                        <p>Guests: {conv.guest_speakers.join(", ")}</p>
                        <p>Duration: {(conv.duration / 60).toFixed(1)}m</p>
                        <p>Turns: {conv.turn_count}</p>
                    </TooltipContent>
                </Tooltip>
                </TooltipProvider>
            ))}

            {/* 2. Topics Row */}
            {flatTopics.map((topic, i) => (
                <TooltipProvider key={`${topic.topic_id}-${i}`}>
                <Tooltip>
                    <TooltipTrigger asChild>
                    <div
                        className="absolute border-r border-background/10 overflow-hidden text-[9px] px-1 whitespace-nowrap text-white/80 hover:brightness-110 cursor-pointer"
                        style={{
                            top: `${CONV_HEIGHT}px`,
                            left: `${topic.start_time * zoomLevel}px`,
                            width: `${topic.duration * zoomLevel}px`,
                            height: `${TOPIC_HEIGHT}px`,
                            backgroundColor: getTopicColor(topic.sentiment),
                        }}
                    >
                        {topic.topic_name}
                    </div>
                    </TooltipTrigger>
                    <TooltipContent className="max-w-xs">
                        <p className="font-bold">{topic.topic_name}</p>
                        <p className="text-xs text-muted-foreground">{topic.sentiment}</p>
                        {topic.key_quotes.length > 0 && (
                            <p className="italic text-xs mt-1">"{topic.key_quotes[0]}"</p>
                        )}
                    </TooltipContent>
                </Tooltip>
                </TooltipProvider>
            ))}

            {/* 3. Clip Suggestions */}
            {clipsResults.clips.map((clip) => {
                const isSelected = selectedClipId === clip.clip_id;
                return (
                    <div key={clip.clip_id}>
                        {/* Clip Segments */}
                        {clip.segments.map((seg, j) => (
                            <div
                                key={`${clip.clip_id}-s${j}`}
                                className={`absolute rounded-sm cursor-pointer hover:scale-y-110 transition-transform ${
                                    isSelected ? "z-10 ring-2 ring-primary" : "opacity-80"
                                }`}
                                style={{
                                    top: `${CONV_HEIGHT + TOPIC_HEIGHT + 5}px`,
                                    left: `${seg.start_time * zoomLevel}px`,
                                    width: `${seg.duration * zoomLevel}px`,
                                    height: `${CLIP_HEIGHT}px`,
                                    backgroundColor: clip.score >= 9 ? "#22c55e" : "#eab308", // Green for 9+, Yellow for others
                                }}
                                onClick={(e) => {
                                    e.stopPropagation(); // prevent seek
                                    selectClip(clip);
                                    // Also seek to start of first segment
                                    setCurrentTime(clip.segments[0].start_time);
                                }}
                            />
                        ))}
                    </div>
                );
            })}

            {/* Playhead */}
            <div 
                className="absolute top-0 bottom-0 w-0.5 bg-red-500 z-50 pointer-events-none"
                style={{
                    left: `${currentTime * zoomLevel}px`,
                }}
            >
                <div className="absolute -top-1 -left-1.5 w-3 h-3 bg-red-500 rounded-full" />
            </div>
        </div>
      </div>
    </div>
  );
}
