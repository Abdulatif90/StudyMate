"use client";

import { CreateOrganization, OrganizationProfile, useOrganization } from "@clerk/nextjs";
import { Users } from "lucide-react";
import { useTranslations } from "next-intl";

/**
 * Team / organization management (Phase 5 foundation). Orgs, members, roles, and
 * invitations are owned entirely by **Clerk Organizations** — we do NOT build our
 * own org/member/invite tables or forms (see docs/DECISIONS.md). This page just
 * mounts Clerk's own management UI:
 *
 * - No active organization -> `<CreateOrganization/>` (the user creates their first
 *   org, or switches into one via the shell's `<OrganizationSwitcher/>`).
 * - Active organization -> `<OrganizationProfile/>`, which is where an admin/teacher
 *   invites members and assigns roles through Clerk's native flow.
 *
 * Clerk components inherit locale from `<ClerkProvider localization>` (already wired
 * in the root layout via `resolveClerkLocalization`), so they follow the app locale.
 */
export default function TeamPage() {
  const t = useTranslations("Team");
  const { isLoaded, organization } = useOrganization();

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <span className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Users className="size-5" aria-hidden />
          </span>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">{t("title")}</h1>
        </div>
        <p className="text-sm text-muted-foreground">
          {isLoaded && !organization ? t("noOrgDescription") : t("description")}
        </p>
      </header>

      {!isLoaded ? (
        <p className="text-sm text-muted-foreground" aria-live="polite">
          {t("loading")}
        </p>
      ) : organization ? (
        // OrganizationProfile is a wide, self-contained card — let it scroll on narrow
        // screens rather than force the content pane to grow horizontally.
        <div className="overflow-x-auto">
          <OrganizationProfile routing="hash" />
        </div>
      ) : (
        <div className="overflow-x-auto">
          <CreateOrganization routing="hash" />
        </div>
      )}
    </div>
  );
}
