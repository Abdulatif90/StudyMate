import { Show } from "@clerk/nextjs";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function Home() {
  const t = useTranslations();
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 p-4 text-center sm:p-8">
      <h1 className="text-3xl font-semibold">StudyMate</h1>
      <p className="text-muted-foreground max-w-md">{t("Home.tagline")}</p>
      <div className="flex flex-col gap-4 sm:flex-row">
        <Show
          when="signed-in"
          fallback={
            <Button
              nativeButton={false}
              render={<Link href="/sign-in">{t("Home.getStarted")}</Link>}
            />
          }
        >
          <Button
            nativeButton={false}
            render={<Link href="/dashboard">{t("Nav.dashboard")}</Link>}
          />
          <Button
            variant="outline"
            nativeButton={false}
            render={<Link href="/subjects">{t("Nav.goToSubjects")}</Link>}
          />
        </Show>
      </div>
    </div>
  );
}
