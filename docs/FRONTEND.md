# FRONTEND.md — Design & Responsive Rules

Prompt/checklist for anyone (human or AI) writing StudyMate frontend.
**Every new page or component MUST follow these rules.** Stack: Next.js 15 App
Router + Tailwind v4 + shadcn/ui, semantic tokens in OKLCH (`src/app/globals.css`),
`.dark` variant enabled.

## 1. Responsive (mobile-first, mandatory)
1. **Mobile-first always.** Base styles target phone; scale up with `sm: md: lg: xl:`.
   Never design desktop-first / never shrink with `max-*` breakpoints.
2. **Breakpoints = Tailwind defaults only** — `sm 640 · md 768 · lg 1024 · xl 1280`.
   Don't invent custom pixel breakpoints.
3. **Page container:** `mx-auto` + `max-w-*`, side padding `px-4 sm:px-6 lg:px-8` — for
   pages OUTSIDE `AppShell` only (home, sign-in, sign-up). Authed pages under
   `AppShell` don't repeat this — see §4.4, the shell already owns it.
4. **Layout via flex/grid + `gap-*`** for spacing — not margins. Grids step up:
   `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3`.
5. **Touch targets ≥ 44px** (`h-10`/`h-11`). Mobile menus/dialogs must be finger-friendly.
6. **Media:** `img` → `max-w-full h-auto`. Text must never cause horizontal scroll;
   only tables/code may scroll inside an `overflow-x-auto` wrapper.
7. **Verify each page at 360px (mobile), 768px (tablet), 1280px (desktop).**

## 2. Colors (best practice)
1. **Semantic tokens only** — `bg-background text-foreground bg-primary
   text-muted-foreground border-border`, etc. **Never** hardcode `#hex`,
   `text-gray-500`, `bg-white` in a component — it breaks dark mode.
2. **Need a new color?** Add a token to both `:root` and `.dark` in `globals.css`
   first, then use it. `globals.css` itself deliberately mixes **hex** (the design
   system's own literal values, kept exact rather than converted) with a few
   remaining **OKLCH** legacy tokens (`--chart-*`) — components never write raw color
   values either way, only token references.
3. **Brand = teal/emerald, gradient as an ACCENT only:**
   - `--primary: #0d9488` (teal-600) / dark `#14b8a6`. `--accent: #10b981` (emerald-500)
     / dark `#34d399`.
   - `--brand-1`/`--brand-2` back the `bg-gradient-brand` utility — reserved for
     primary buttons, the active sidebar-nav item, the "most popular" plan badge, and
     the brand mark. **Never** a background/hero panel; the gradient is jewelry, not
     wallpaper.
   - Pick readable `--primary-foreground`/`--accent-foreground` per theme.
4. **Contrast = WCAG AA (mandatory):** body text ≥ 4.5:1, large text/icons ≥ 3:1.
   `muted-foreground` is for secondary text only.
5. **Meaning via tokens, THREE shades per status:** `--destructive`/`--success`/
   `--warning` (text/icon color) each pair with a `-bg` tint (card/badge backgrounds)
   and — for success/warning — a `-fill` (progress-bar fill, a stronger, more
   saturated shade than the text color). **Never rely on color alone** — pair with an
   icon/label (color-blind & accessibility).
6. **Focus visible:** interactive elements keep `focus-visible:ring-2 ring-ring`.
   Never remove focus outlines.
7. **Neutrals are warm, never pure gray** — `--background`/`--card`/`--border`/
   `--muted-foreground` all carry a slight warmth, both themes.
8. **Charts use a real categorical ramp.** `--chart-1..5` must be distinguishable hues
   (not the stock grayscale), contrast-checked in light and dark. Load the `dataviz`
   skill before choosing chart colors or building any meter/stat tile.

## 3. Overlays, confirmations & feedback (mandatory)
Stack note: this repo uses the **Base UI** shadcn variant — primitives come from
`@base-ui/react/*` (`/alert-dialog`, `/dialog`, `/toast`, `/select`, `/menu`), wrapped as
`src/components/ui/*`. Reuse those wrappers before hand-rolling.
1. **Never `window.confirm` / `window.alert` / `alert()`.** Destructive or irreversible
   actions use the `ui/alert-dialog` confirmation (via the shared `useConfirm` helper):
   title, description, a destructive confirm label, and a cancel.
2. **Never surface transient failures as inline `<p className="text-destructive">`.**
   Route mutation success/failure through the `toast()` helper (Base UI `ui/toast`, one
   `<Toaster/>` in `app/providers.tsx`). Inline text is only for persistent in-context state.
3. **Exception — the 402 plan-limit prompt stays inline.** `<UpgradePrompt>` is a
   conversion CTA, not a transient error; keep it in-flow (restyled), optionally mirrored
   by a toast with an "Upgrade" action.
4. **Overlays are finger-friendly + accessible:** focus-trapped, Esc-dismissable, ≥44px
   targets, checked in light + dark.

## 4. App shell & navigation (mandatory)
1. **One shared shell, no per-page headers.** Authed pages render inside `AppShell` —
   a fixed left sidebar on `lg`+ (236px, **permanently dark** `bg-sidebar`,
   REGARDLESS of the app's own light/dark theme — see FRONTEND.md's design-prompt
   source): brand mark + wordmark, vertical nav (Dashboard · Subjects · Plan &
   billing), a compact usage widget, and a profile row pinned at the bottom. Below
   `lg` it collapses into a slim dark top bar + `ui/menu` dropdown. Theme toggle +
   language switcher live in the content pane's utility row (or the mobile top bar),
   not the sidebar — both use the general `--background`/`--border` tokens, which
   would look wrong pinned against the sidebar's own separate always-dark tokens.
   Do not hand-roll a page-local header/nav.
2. **Every primary destination reachable from the shell on every screen** — billing/
   upgrade included.
3. **Dark-mode toggle is a first-class control** (drives `.dark` on the CONTENT
   tokens only — the sidebar never changes); persist the choice.
4. **The shell owns the content pane's outer width/padding** (`max-w-[920px]`,
   `px-6 py-8 sm:px-12`, registered once in `AppShell`'s `<main>`) — a page's own
   top-level element must NOT also wrap itself in `mx-auto max-w-*`/`p-4 sm:p-8`;
   that double-constrains the width and doubles the padding. A page that needs its
   own internal layout (e.g. a sidebar+main split) keeps ONLY the structural classes
   (`flex md:flex-row gap-*`), not a competing width/padding wrapper.
5. **Cards, not plain `<a>`/`<Link>` text, for any destination that's really a row in
   a list** (a subject, a plan, a stat) — icon badge + label(+meta) + a chevron or
   action, using `Card`'s `interactive` prop (hover lift + brand-tinted ring) so the
   whole row visibly reads as a control. Reserve bare text links for genuinely
   secondary, inline actions (e.g. "View all").

## 5. General
1. Spacing, radius, color — Tailwind scale & tokens only. No magic pixel values.
   The base spacing scale (4/8/12/16/24/32/48px) already matches Tailwind's own
   `spacing(1..12)` multiples one-to-one — never reach for an arbitrary value where
   `p-1`…`p-12` already lands on the target px value.
2. Every component checked in **both** light and dark.
3. Reuse shadcn/ui primitives in `src/components/ui` before hand-rolling.
4. **Every interactive surface needs a hover transition** (120–250ms — Tailwind's
   `transition-*` utilities default to 150ms, already inside range, so an explicit
   duration is rarely needed) and **`:active` gives real press feedback**
   (`Button`'s base class already does this app-wide — don't reintroduce a
   per-component press effect). No decorative animation that doesn't communicate
   state (no idle floating/pulsing on a working app screen — marketing/landing pages
   only). Do reserve one genuine "on-load" animation for numeric progress bars
   (`AnimatedProgressBar`): they fill from 0 to the real value once, never jump
   instantly.
