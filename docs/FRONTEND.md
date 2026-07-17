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
3. **Page container:** `mx-auto` + `max-w-*`, side padding `px-4 sm:px-6 lg:px-8`.
4. **Layout via flex/grid + `gap-*`** for spacing — not margins. Grids step up:
   `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3`.
5. **Touch targets ≥ 44px** (`h-10`/`h-11`). Mobile menus/dialogs must be finger-friendly.
6. **Media:** `img` → `max-w-full h-auto`. Text must never cause horizontal scroll;
   only tables/code may scroll inside an `overflow-x-auto` wrapper.
7. **Verify each page at 360px (mobile), 768px (tablet), 1280px (desktop).**

## 2. Colors (best practice)
1. **Semantic tokens only** — `bg-background text-foreground bg-primary
   text-muted-foreground border-border`, etc. **Never** hardcode `#hex`,
   `text-gray-500`, `bg-white` — it breaks dark mode.
2. **Need a new color?** Add a token to both `:root` and `.dark` in `globals.css`
   first, then use it. Keep everything in **OKLCH** — no hex mixed in.
3. **Brand primary = indigo/blue:**
   - Light: `--primary: oklch(0.55 0.18 265)`
   - Dark: `--primary: oklch(0.70 0.16 265)`
   - Pick readable `--primary-foreground` (near-white on light primary).
4. **Contrast = WCAG AA (mandatory):** body text ≥ 4.5:1, large text/icons ≥ 3:1.
   `muted-foreground` is for secondary text only.
5. **Meaning via tokens:** error → `destructive`; add `--success` / `--warning`
   tokens when needed. **Never rely on color alone** — pair with an icon/label
   (color-blind & accessibility).
6. **Focus visible:** interactive elements keep `focus-visible:ring-2 ring-ring`.
   Never remove focus outlines.
7. **Accent = teal (calm-academic direction).** Primary stays indigo (rule 3); the
   accent is a distinct teal, and neutrals carry a slight warmth (a hint of chroma in
   `--muted`/`--secondary`/`--border`), never pure gray. Add `--warning` /
   `--warning-foreground` alongside `--destructive`/`--success`. All in OKLCH, both
   `:root` and `.dark`.
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
1. **One shared shell, no per-page headers.** Authed pages render inside `AppShell`
   (persistent nav: Dashboard · Subjects · Plan & billing · theme toggle · language
   switcher slot · `UserButton`). Do not hand-roll a page-local header/nav.
2. **Every primary destination reachable from the shell on every screen** — billing/
   upgrade included.
3. **Dark-mode toggle is a first-class control** in the shell (drives `.dark`); persist
   the choice.
4. Mobile-first: the nav collapses into a `ui/menu` sheet/dropdown below `sm`.

## 5. General
1. Spacing, radius, color — Tailwind scale & tokens only. No magic pixel values.
2. Every component checked in **both** light and dark.
3. Reuse shadcn/ui primitives in `src/components/ui` before hand-rolling.
