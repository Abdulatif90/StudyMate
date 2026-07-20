"use client";

import { useMutation } from "@tanstack/react-query";
import { Globe } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/components/ui/toast";
import { useApiClient } from "@/lib/api/useApiClient";
import { researchSourceLabel } from "@/lib/researchSource";
import type { components } from "@/lib/api/schema";

type ResearchResponse = components["schemas"]["ResearchResponse"];

// Same markdown config as the Ask answer bubble (components/answer-message.tsx) —
// deliberately no rehype-raw, so any HTML in the answer stays escaped/safe.
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

export default function ResearchPage() {
  const t = useTranslations("Research");
  const api = useApiClient();
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<ResearchResponse | null>(null);

  // POST /research is a bounded agentic web-search loop (Tavily + Claude) and can
  // take 5-20s — the UI below disables the input/button and shows a clear
  // "researching…" state for the whole mutation, not just a spinner on the button.
  const research = useMutation({
    mutationFn: async (submittedQuery: string) => {
      const { data, error } = await api.POST("/research", {
        body: { query: submittedQuery },
      });
      if (error) throw error;
      return data;
    },
    onSuccess: (data) => {
      setResult(data);
    },
    onError: () => {
      toast.error(t("error"));
    },
  });

  const trimmedQuery = query.trim();

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!trimmedQuery || research.isPending) return;
    research.mutate(trimmedQuery);
  }

  return (
    <div>
      <div className="mb-6 flex items-start gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-gradient-brand text-white">
          <Globe className="size-5" aria-hidden />
        </span>
        <div>
          <h1 className="text-[22px] font-semibold">{t("heading")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t("subheading")}</p>
        </div>
      </div>

      <form className="flex flex-col gap-2" onSubmit={handleSubmit}>
        <Textarea
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t("placeholder")}
          disabled={research.isPending}
        />
        <Button type="submit" className="self-end" disabled={!trimmedQuery || research.isPending}>
          {research.isPending ? t("researching") : t("button")}
        </Button>
      </form>

      {research.isPending && (
        <p className="mt-4 text-sm text-muted-foreground">{t("researching")}</p>
      )}

      {research.isError && !research.isPending && (
        <p className="mt-4 text-sm text-destructive">{t("error")}</p>
      )}

      {result && !research.isPending && (
        <Card className="mt-6">
          <CardContent className="flex flex-col gap-4 py-4">
            <div className="min-w-0 text-sm break-words [&_ol_ol]:list-[lower-alpha] [&_ul_ul]:list-[circle]">
              <ReactMarkdown components={markdownComponents}>{result.answer}</ReactMarkdown>
            </div>

            {result.sources.length > 0 && (
              <div>
                <h2 className="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                  {t("sourcesHeading")}
                </h2>
                <ul className="flex flex-col gap-1.5">
                  {result.sources.map((source, index) => (
                    <li key={`${source.url}-${index}`} className="min-w-0">
                      <a
                        href={source.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm break-all text-primary underline-offset-2 hover:underline"
                      >
                        {researchSourceLabel(source)}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
