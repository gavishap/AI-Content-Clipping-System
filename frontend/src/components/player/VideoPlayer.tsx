"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from 'next/dynamic';
import { useAppStore } from "@/lib/store";
import { FinalClip } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Play, Pause } from "lucide-react";

// Dynamic import for ReactPlayer to avoid SSR issues
const ReactPlayer = dynamic(() => import("react-player"), { ssr: false });

// Placeholder URL - replace with actual episode URL
const VIDEO_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"; // Placeholder

export function VideoPlayer() {
  // Use a ref to the player component instance (ReactPlayer handles the internal ref)
  const playerRef = useRef<any>(null); // Type as any for dynamic import wrapper
  const [isReady, setIsReady] = useState(false);
  
  // Global State
  const { 
    currentTime, 
    isPlaying, 
    setIsPlaying, 
    setCurrentTime, 
    setDuration,
    selectedClip,
    isCompositePreview
  } = useAppStore();

  // Handle Seek from external controls (timeline click)
  useEffect(() => {
    if (playerRef.current && Math.abs(playerRef.current.getCurrentTime() - currentTime) > 0.5) {
      if (!isPlaying) {
          playerRef.current.seekTo(currentTime, "seconds");
      }
    }
  }, [currentTime, isPlaying]);

  // Composite Logic
  const handleProgress = (state: { playedSeconds: number }) => {
    if (isPlaying) {
        if (Math.abs(state.playedSeconds - currentTime) > 0.1) {
             setCurrentTime(state.playedSeconds);
        }
    }

    if (isCompositePreview && selectedClip && selectedClip.segments.length > 1) {
        checkCompositeJump(state.playedSeconds, selectedClip);
    }
  };

  const checkCompositeJump = (current: number, clip: FinalClip) => {
      for (let i = 0; i < clip.segments.length; i++) {
          const seg = clip.segments[i];
          const nextSeg = clip.segments[i+1];
          
          if (current >= seg.start_time && current < seg.end_time) {
              return;
          }
          
          if (current >= seg.end_time && current < seg.end_time + 1.0) {
              if (nextSeg) {
                  console.log("Composite jump to next segment:", nextSeg.start_time);
                  playerRef.current?.seekTo(nextSeg.start_time, "seconds");
                  return;
              } else {
                  console.log("Composite end reached");
                  setIsPlaying(false);
                  return;
              }
          }
      }
  };

  return (
    <div className="w-full h-full flex flex-col bg-black rounded-lg overflow-hidden border border-border">
      <div className="relative flex-1 min-h-[300px]">
        <ReactPlayer
          ref={playerRef}
          url={VIDEO_URL}
          width="100%"
          height="100%"
          playing={isPlaying}
          controls={false}
          onReady={() => setIsReady(true)}
          onDuration={(d: number) => setDuration(d)}
          onProgress={handleProgress}
          progressInterval={100}
        />
      </div>
      
      <div className="h-14 bg-card border-t border-border flex items-center px-4 gap-4">
        <Button 
            variant="ghost" 
            size="icon" 
            onClick={() => setIsPlaying(!isPlaying)}
        >
            {isPlaying ? <Pause className="h-5 w-5" /> : <Play className="h-5 w-5" />}
        </Button>
        
        <div className="flex-1">
            <span className="text-sm font-mono text-muted-foreground">
                {formatTime(currentTime)}
            </span>
        </div>
      </div>
    </div>
  );
}

function formatTime(seconds: number) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}
