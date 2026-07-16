"use client";

import { Copy, Pencil, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { formatRelativeTime } from "@/lib/relativeTime";

export function QuestionMessage({
  text,
  timestamp,
  isEditing,
  pending = false,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  onDelete,
}: {
  text: string;
  timestamp: string;
  isEditing: boolean;
  /** Shown while the edited/new question has been sent but the answer hasn't
   * come back yet — no actions make sense on a not-yet-saved question. */
  pending?: boolean;
  onStartEdit: () => void;
  onCancelEdit: () => void;
  onSaveEdit: (newText: string) => void;
  onDelete: () => void;
}) {
  const [draft, setDraft] = useState(text);

  // Reset the draft to the current question text each time editing (re)starts,
  // so switching which question is being edited doesn't leak a stale draft.
  useEffect(() => {
    if (isEditing) setDraft(text);
  }, [isEditing, text]);

  if (isEditing) {
    return (
      <Card className="bg-muted/50">
        <CardContent className="flex flex-col gap-2 py-4">
          <Textarea
            autoFocus
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
          />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onCancelEdit}>
              Cancel
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={!draft.trim()}
              onClick={() => onSaveEdit(draft.trim())}
            >
              Save & resend
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (pending) {
    return (
      <Card className="bg-muted/50">
        <CardContent className="flex flex-col gap-2 py-4">
          <p className="min-w-0 font-medium break-words">{text}</p>
          <span className="text-xs text-muted-foreground">Sending…</span>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="bg-muted/50">
      <CardContent className="flex flex-col gap-2 py-4">
        <p className="min-w-0 font-medium break-words">{text}</p>
        <div className="flex flex-col items-end gap-1">
          <span className="text-xs text-muted-foreground">{formatRelativeTime(timestamp)}</span>
          <div className="flex flex-wrap items-center gap-1">
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Copy question"
              onClick={() => navigator.clipboard.writeText(text)}
            >
              <Copy className="size-3.5" />
            </Button>
            <Button variant="ghost" size="icon-sm" aria-label="Edit question" onClick={onStartEdit}>
              <Pencil className="size-3.5" />
            </Button>
            <Button variant="ghost" size="icon-sm" aria-label="Delete question" onClick={onDelete}>
              <Trash2 className="size-3.5" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
