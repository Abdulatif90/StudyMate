import {
  BookOpen,
  CreditCard,
  LayoutDashboard,
  LifeBuoy,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  /** Key into the `Nav` next-intl namespace. */
  translationKey: "dashboard" | "subjects" | "billing" | "support";
  icon: LucideIcon;
}

/** Every primary destination reachable from the shell on every screen (FRONTEND.md §4.2). */
export const NAV_ITEMS: readonly NavItem[] = [
  { href: "/dashboard", translationKey: "dashboard", icon: LayoutDashboard },
  { href: "/subjects", translationKey: "subjects", icon: BookOpen },
  { href: "/billing", translationKey: "billing", icon: CreditCard },
  { href: "/support", translationKey: "support", icon: LifeBuoy },
];

/**
 * Whether `href` should render as the active nav item for the current `pathname`.
 * Matches the destination itself AND any of its sub-routes (`/subjects` stays active on
 * `/subjects/abc123/quizzes`) via a trailing-slash-bounded prefix check — exact equality
 * alone would leave every subject-scoped page with no active nav item at all. The
 * trailing slash in the prefix check also stops `/subjects` from matching an unrelated
 * route that merely shares the prefix (e.g. a hypothetical `/subjects-archive`).
 */
export function isNavItemActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}
