import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { documentStatusRows } from "@/lib/documentProgress";
import { masteryRows, percentMature } from "@/lib/flashcardMastery";
import type { components } from "@/lib/api/schema";

type DocumentStatusCounts = components["schemas"]["DocumentStatusCounts"];
type FlashcardProgress = components["schemas"]["FlashcardProgress"];

interface ProgressStatsProps {
  documents: DocumentStatusCounts;
  flashcards: FlashcardProgress;
  quizCount: number;
}

// Status encoding, not an arbitrary categorical palette — these are the app's own
// pre-existing semantic tokens (muted = not started, primary = in progress, success =
// well-learned), reused here rather than a new hue set. Every segment is still paired
// with a visible label/count in the legend below the bar, never color alone.
const MASTERY_TOKEN: Record<string, string> = {
  new: "bg-muted-foreground/30",
  learning: "bg-primary",
  mature: "bg-success",
};

function StatTile({
  label,
  value,
  sublabel,
}: {
  label: string;
  value: number;
  sublabel?: string;
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-1 py-4">
        <p className="text-2xl font-semibold">{value}</p>
        <p className="text-sm text-muted-foreground">{label}</p>
        {sublabel && <p className="text-xs text-muted-foreground">{sublabel}</p>}
      </CardContent>
    </Card>
  );
}

export function ProgressStats({ documents, flashcards, quizCount }: ProgressStatsProps) {
  const rows = masteryRows(flashcards);
  const mature = percentMature(flashcards);

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatTile label="Documents" value={documents.total} />
        <StatTile
          label="Flashcards"
          value={flashcards.total}
          sublabel={flashcards.due > 0 ? `${flashcards.due} due for review` : undefined}
        />
        <StatTile label="Quizzes generated" value={quizCount} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Documents by status</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {documents.total === 0 ? (
            <p className="text-sm text-muted-foreground">No documents yet.</p>
          ) : (
            documentStatusRows(documents).map((row) => (
              <Badge key={row.key} variant={row.variant}>
                {row.label}: {row.count}
              </Badge>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Flashcard mastery</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {flashcards.total === 0 ? (
            <p className="text-sm text-muted-foreground">No flashcards yet.</p>
          ) : (
            <>
              <div
                className="flex h-3 w-full gap-0.5 overflow-hidden rounded-full bg-muted"
                role="img"
                aria-label={`${mature}% of flashcards are mature — ${rows
                  .map((row) => `${row.label} ${row.count}`)
                  .join(", ")}`}
              >
                {rows
                  .filter((row) => row.count > 0)
                  .map((row) => (
                    <div
                      key={row.key}
                      className={cn("h-full", MASTERY_TOKEN[row.key])}
                      style={{ flexGrow: row.count }}
                    />
                  ))}
              </div>
              <ul className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
                {rows.map((row) => (
                  <li key={row.key} className="flex items-center gap-1.5">
                    <span
                      aria-hidden
                      className={cn("size-2 shrink-0 rounded-full", MASTERY_TOKEN[row.key])}
                    />
                    <span className="text-muted-foreground">
                      {row.label} ({row.status}):{" "}
                      <span className="font-medium text-foreground">{row.count}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
