"use client";

import { useAppStore } from "@/lib/store";
import { clipsResults } from "@/lib/data";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Play, Download, Scissors } from "lucide-react";

export function ClipSidebar() {
  const { 
    selectedClip, 
    selectClip, 
    updateSelectedClip, 
    setIsPlaying, 
    setCurrentTime,
    toggleCompositePreview,
    isCompositePreview 
  } = useAppStore();

  const handleSegmentChange = (index: number, field: 'start_time' | 'end_time', value: string) => {
    if (!selectedClip) return;
    const numVal = parseFloat(value);
    if (isNaN(numVal)) return;

    const newSegments = [...selectedClip.segments];
    newSegments[index] = { ...newSegments[index], [field]: numVal };
    // Recalc duration
    newSegments[index].duration = newSegments[index].end_time - newSegments[index].start_time;
    
    updateSelectedClip({ segments: newSegments });
  };

  const handlePreview = () => {
      if (!selectedClip) return;
      // Start from beginning of first segment
      setCurrentTime(selectedClip.segments[0].start_time);
      toggleCompositePreview(true);
      setIsPlaying(true);
  };

  return (
    <div className="flex flex-col h-full bg-card border-l border-border">
      <div className="p-4 border-b border-border bg-muted/20">
        <h2 className="font-bold text-lg">Suggested Clips ({clipsResults.total_clips})</h2>
      </div>

      <div className="flex-1 min-h-0 flex flex-col">
        {selectedClip ? (
          <div className="flex flex-col h-full">
            <ScrollArea className="flex-1 p-4">
                <div className="space-y-6">
                    <div>
                        <Button variant="ghost" size="sm" onClick={() => selectClip(null)} className="mb-2 -ml-2 text-muted-foreground">
                            ← Back to List
                        </Button>
                        <h3 className="text-xl font-bold leading-tight mb-2">{selectedClip.title}</h3>
                        <div className="flex gap-2 mb-4">
                            <Badge variant={selectedClip.score >= 9 ? "default" : "secondary"}>
                                Score: {selectedClip.score}
                            </Badge>
                            <Badge variant="outline">{selectedClip.clip_type}</Badge>
                            <Badge variant="outline">{selectedClip.assembly}</Badge>
                        </div>
                        <p className="text-sm text-muted-foreground mb-4">{selectedClip.narrative}</p>
                    </div>

                    <div className="space-y-4">
                        <div className="flex items-center justify-between">
                            <h4 className="font-semibold flex items-center gap-2">
                                <Scissors className="w-4 h-4" /> Segments
                            </h4>
                            <Button size="sm" onClick={handlePreview} variant={isCompositePreview ? "default" : "outline"}>
                                <Play className="w-3 h-3 mr-2" /> Preview Composite
                            </Button>
                        </div>
                        
                        {selectedClip.segments.map((seg, i) => (
                            <Card key={i} className="bg-muted/30">
                                <CardContent className="p-3 space-y-3">
                                    <div className="flex items-center justify-between text-xs font-mono text-muted-foreground">
                                        <span>Segment {i+1} ({seg.purpose})</span>
                                        <span>{seg.duration.toFixed(1)}s</span>
                                    </div>
                                    <div className="grid grid-cols-2 gap-2">
                                        <div>
                                            <Label className="text-xs">Start</Label>
                                            <Input 
                                                className="h-8 font-mono text-xs"
                                                type="number" 
                                                value={seg.start_time} 
                                                onChange={(e) => handleSegmentChange(i, 'start_time', e.target.value)}
                                            />
                                        </div>
                                        <div>
                                            <Label className="text-xs">End</Label>
                                            <Input 
                                                className="h-8 font-mono text-xs"
                                                type="number" 
                                                value={seg.end_time} 
                                                onChange={(e) => handleSegmentChange(i, 'end_time', e.target.value)}
                                            />
                                        </div>
                                    </div>
                                    <p className="text-xs italic text-muted-foreground border-l-2 border-primary/20 pl-2">
                                        "{seg.transcript_excerpt.substring(0, 80)}..."
                                    </p>
                                </CardContent>
                            </Card>
                        ))}
                    </div>
                </div>
            </ScrollArea>
            <div className="p-4 border-t border-border bg-background">
                <Button className="w-full" size="lg">
                    <Download className="w-4 h-4 mr-2" /> Export Clip
                </Button>
            </div>
          </div>
        ) : (
          <ScrollArea className="flex-1">
            <div className="p-2 space-y-2">
              {clipsResults.clips.map((clip) => (
                <Card 
                    key={clip.clip_id} 
                    className="cursor-pointer hover:bg-muted/50 transition-colors"
                    onClick={() => selectClip(clip)}
                >
                  <CardContent className="p-3">
                    <div className="flex justify-between items-start mb-1">
                        <span className="font-semibold text-sm line-clamp-2">{clip.title}</span>
                        <Badge variant={clip.score >= 9 ? "default" : "secondary"} className="ml-2 shrink-0 text-[10px]">
                            {clip.score}
                        </Badge>
                    </div>
                    <div className="flex gap-2 text-[10px] text-muted-foreground">
                        <span>{clip.clip_type}</span>
                        <span>•</span>
                        <span>{clip.assembly}</span>
                        <span>•</span>
                        <span>{clip.total_duration.toFixed(0)}s</span>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </ScrollArea>
        )}
      </div>
    </div>
  );
}
