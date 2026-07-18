"use client";

import { ChevronDown, LifeBuoy } from "lucide-react";
import { useTranslations } from "next-intl";
import { Card, CardContent } from "@/components/ui/card";

interface FaqItem {
  /** Key into `Support.questions`. */
  questionKey: string;
  /** Key into `Support.answers`. */
  answerKey: string;
}

interface FaqSection {
  /** Key into `Support.sections`. */
  titleKey: string;
  items: FaqItem[];
}

// Static FAQ content — covers only real, shipped features (subjects, upload +
// auto-summary, Ask/cited RAG Q&A, quiz, flashcards + SM-2, progress, billing).
// No backend, no CMS: this is the whole "content model" (KISS/YAGNI).
const FAQ_SECTIONS: FaqSection[] = [
  {
    titleKey: "gettingStarted",
    items: [
      { questionKey: "whatIsStudyMate", answerKey: "whatIsStudyMate" },
      { questionKey: "howToStart", answerKey: "howToStart" },
      { questionKey: "fileTypes", answerKey: "fileTypes" },
    ],
  },
  {
    titleKey: "studyTools",
    items: [
      { questionKey: "howAskWorks", answerKey: "howAskWorks" },
      { questionKey: "unansweredQuestions", answerKey: "unansweredQuestions" },
      { questionKey: "howQuizWorks", answerKey: "howQuizWorks" },
      { questionKey: "howFlashcardsWork", answerKey: "howFlashcardsWork" },
    ],
  },
  {
    titleKey: "progress",
    items: [{ questionKey: "whatIsProgress", answerKey: "whatIsProgress" }],
  },
  {
    titleKey: "billing",
    items: [
      { questionKey: "whatPlansExist", answerKey: "whatPlansExist" },
      { questionKey: "howToUpgrade", answerKey: "howToUpgrade" },
      { questionKey: "whatHappensAtLimit", answerKey: "whatHappensAtLimit" },
    ],
  },
];

export default function SupportPage() {
  const t = useTranslations("Support");

  return (
    <div>
      <div className="mb-6 flex items-start gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-gradient-brand text-white">
          <LifeBuoy className="size-5" aria-hidden />
        </span>
        <div>
          <h1 className="text-[22px] font-semibold">{t("heading")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t("subheading")}</p>
        </div>
      </div>

      <div className="flex flex-col gap-8">
        {FAQ_SECTIONS.map((section) => (
          <div key={section.titleKey}>
            <h2 className="mb-3 text-[13px] font-semibold tracking-wide text-muted-foreground uppercase">
              {t(`sections.${section.titleKey}`)}
            </h2>
            <Card>
              <CardContent className="divide-y divide-border">
                {section.items.map((item) => (
                  <details key={item.questionKey} className="group">
                    <summary
                      className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded-md py-3 text-sm font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden"
                    >
                      {t(`questions.${item.questionKey}`)}
                      <ChevronDown
                        className="size-4 shrink-0 text-muted-foreground transition-transform duration-150 group-open:rotate-180"
                        aria-hidden
                      />
                    </summary>
                    <p className="pb-4 text-sm text-muted-foreground">
                      {t(`answers.${item.answerKey}`)}
                    </p>
                  </details>
                ))}
              </CardContent>
            </Card>
          </div>
        ))}
      </div>
    </div>
  );
}
