"use client";

import { Copy, Pin, Volume2 } from "lucide-react";
import { useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { formatRelativeTime } from "@/lib/relativeTime";
import { simplifyCitations } from "@/lib/simplifyCitations";

const markdownComponents: Components = {
  p: (props) => <p className="mb-2 last:mb-0" {...props} />,
  strong: (props) => <strong className="font-semibold" {...props} />,
  h1: (props) => <h4 className="mt-3 mb-1 text-sm font-semibold first:mt-0" {...props} />,
  h2: (props) => <h4 className="mt-3 mb-1 text-sm font-semibold first:mt-0" {...props} />,
  h3: (props) => <h4 className="mt-3 mb-1 text-sm font-semibold first:mt-0" {...props} />,
  ul: (props) => <ul className="mb-2 list-disc pl-5 last:mb-0" {...props} />,
  ol: (props) => <ol className="mb-2 list-decimal pl-5 last:mb-0" {...props} />,
  li: (props) => <li className="mb-1 last:mb-0" {...props} />,
};

export function AnswerMessage({
  text,
  timestamp,
  pinned,
  onTogglePin,
}: {
  text: string;
  timestamp: string;
  pinned: boolean;
  onTogglePin: () => void;
}) {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const displayText = simplifyCitations(text);

  function readAloud() {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(displayText);
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);
    setIsSpeaking(true);
    window.speechSynthesis.speak(utterance);
  }

  function stopReading() {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    setIsSpeaking(false);
  }

  return (
    <Card className={pinned ? "ring-1 ring-primary" : undefined}>
      <CardContent className="flex flex-col gap-2 py-4">
        <div className="min-w-0 text-sm break-words [&_ol_ol]:list-[lower-alpha] [&_ul_ul]:list-[circle]">
          <ReactMarkdown components={markdownComponents}>{displayText}</ReactMarkdown>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className="text-xs text-muted-foreground">{formatRelativeTime(timestamp)}</span>
          <div className="flex flex-wrap items-center gap-1">
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Copy answer"
              onClick={() => navigator.clipboard.writeText(displayText)}
            >
              <Copy className="size-3.5" />
            </Button>
            <Button
              variant={pinned ? "secondary" : "ghost"}
              size="icon-sm"
              aria-label={pinned ? "Unpin answer" : "Pin answer"}
              onClick={onTogglePin}
            >
              <Pin className="size-3.5" />
            </Button>
            <Button
              variant={isSpeaking ? "secondary" : "ghost"}
              size="icon-sm"
              aria-label={isSpeaking ? "Stop reading aloud" : "Read answer aloud"}
              onClick={isSpeaking ? stopReading : readAloud}
            >
              <Volume2 className="size-3.5" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
