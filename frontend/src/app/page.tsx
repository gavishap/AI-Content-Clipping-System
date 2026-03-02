"use client";

import { VideoPlayer } from "@/components/player/VideoPlayer";
import { Timeline } from "@/components/timeline/Timeline";
import { ClipSidebar } from "@/components/clips/ClipSidebar";
import { conversationMap, topicMap, clipsResults, VIDEO_DURATION } from "@/lib/data";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { 
  BarChart, 
  Clock, 
  MessageSquare, 
  Scissors, 
  Share2 
} from "lucide-react";

export default function Home() {
  return (
    <div className="h-screen flex flex-col bg-background text-foreground overflow-hidden">
      {/* Header */}
      <header className="h-14 shrink-0 border-b border-border bg-card flex items-center px-4 justify-between z-10">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 bg-primary rounded-md flex items-center justify-center font-bold text-primary-foreground">
              NM
            </div>
            <span className="font-bold text-lg hidden md:inline">Nick Matau Clipper</span>
          </div>
          <Separator orientation="vertical" className="h-6" />
          <div className="flex gap-4 text-xs text-muted-foreground">
            <div className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              <span>{(VIDEO_DURATION / 60).toFixed(0)} min</span>
            </div>
            <div className="flex items-center gap-1">
              <MessageSquare className="w-3 h-3" />
              <span>{conversationMap.total_conversations} Convos</span>
            </div>
            <div className="flex items-center gap-1">
              <BarChart className="w-3 h-3" />
              <span>{topicMap.total_topics} Topics</span>
            </div>
            <div className="flex items-center gap-1">
              <Scissors className="w-3 h-3" />
              <span>{clipsResults.total_clips} Clips</span>
            </div>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm">
            <Share2 className="w-4 h-4 mr-2" />
            Share Report
          </Button>
          <Button size="sm">
            Export All Clips
          </Button>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Player + Timeline */}
        <div className="flex-1 flex flex-col min-w-0 bg-muted/5">
          <div className="flex-1 p-4 overflow-hidden relative">
            {/* Player Container */}
            <div className="w-full h-full max-w-5xl mx-auto shadow-2xl rounded-lg overflow-hidden">
              <VideoPlayer />
            </div>
          </div>
          
          <div className="h-[200px] shrink-0 border-t border-border bg-background z-10">
            <Timeline />
          </div>
        </div>

        {/* Right: Sidebar */}
        <div className="w-[400px] shrink-0 border-l border-border bg-card z-20 shadow-xl">
          <ClipSidebar />
        </div>
      </div>
    </div>
  );
}
