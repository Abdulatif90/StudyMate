# StudyMate redesign — implementation prompt

Apply this design system to the StudyMate app (Dashboard, Subjects, Plan & billing pages). Reference files: `studymate-redesign-v2.html` (final layout, use this one) and `studymate-redesign.html` (earlier top-nav version, ignore).

## Layout

Replace the top navbar with a fixed left sidebar (236px wide, dark background `#171A19`, white text). Sidebar contains, top to bottom: brand mark + wordmark, vertical nav (Dashboard / Subjects / Plan and billing) with icon + label per item, a compact "usage" widget (mini progress bars for subjects and daily generations with a "Manage plan" link), and a user profile row pinned at the bottom (avatar initials + name + current plan).

Main content area sits to the right of the sidebar with generous padding (32px vertical, 48px horizontal), max content width ~920px.

## Color tokens

```
--brand-1: #0D9488   /* teal-600 */
--brand-2: #10B981   /* emerald-500 */
--brand-grad: linear-gradient(135deg, var(--brand-1), var(--brand-2))

--bg: #FAFAF9
--sidebar: #171A19
--card: #FFFFFF
--border: #E7E5E0
--text: #171717
--text-secondary: #6B6A65
--text-muted: #9C9A93

--amber: #B45309    --amber-bg: #FEF3E2   --amber-fill: #F59E0B   /* usage nearing limit */
--green: #166534    --green-bg: #ECFDF3   --green-fill: #22C55E   /* usage healthy */
--red: #B91C1C       --red-bg: #FEF2F2                            /* destructive actions */

--shadow-sm: 0 1px 2px rgba(20,20,10,0.05)
--shadow-md: 0 6px 20px rgba(20,20,10,0.08)
```

Use the brand gradient only for: primary buttons, active nav state accents, the "most popular" plan badge, and the brand mark icon. Do not apply it to large background areas (no full gradient navbar/hero) — the brand color should read as an accent, not wallpaper.

## Spacing and radius

8px base scale: 4 / 8 / 12 / 16 / 24 / 32 / 48px. Apply consistently to card padding, gaps between cards, and section margins — no arbitrary spacing values. Card radius: 10–12px. Button/input radius: 8px. Pills/badges: full radius (20px).

## Typography

Sans-serif throughout (system font stack) for all UI text — body, nav, buttons, headings. Reserve serif (e.g. Georgia) only for the brand wordmark in the sidebar, nowhere else. Heading hierarchy by weight and size, not by font family switch: page title 22px/600, section labels 13px/600 uppercase with letter-spacing, body 13–14px/400, labels 12–13px/500.

## Icons

Use an outline SVG icon set (Tabler icons or Heroicons outline) at 16–18px, stroke-width ~1.8–2. No emoji anywhere in the UI. Icon-only buttons get a colored tint background matching their semantic role (e.g. delete button: `--red-bg` background, `--red` icon color).

## Components

**Buttons** — three variants: `primary` (brand gradient fill, white text, used once per view max for the main CTA), `ghost` (transparent bg, border, used for secondary actions), `icon` (32×32px, tinted bg, for destructive/compact actions). All buttons: `transition: transform 0.12s, box-shadow 0.2s, filter 0.2s`; `:hover` raises shadow and brightens slightly; `:active` scales to 0.97.

**Stat cards** (dashboard usage summary) — 2-column grid, white card, label + bold value pair at top (value colored amber/green based on how close to the limit), thin progress track (6px, rounded) below. Do not duplicate this full detail on the billing page — billing page shows the same data in a fuller comparison layout instead; dashboard only needs the condensed version.

**Subject cards** — horizontal layout: icon badge (36px, tinted background per subject/category, rounded 9px) + title + meta line (document/due/quiz counts), chevron-right affordance on the far right indicating it's clickable. Hover: lift (`translateY(-1px)`) + shadow + border tint toward brand color.

**Plan cards** (billing page) — 2-column grid, white card with border, the recommended plan gets a 1.5px brand-colored border and a small pill badge ("Most popular") overlapping the top edge. Each card: plan name, price (large, bold) with `/month` in muted smaller text, a checklist of included features (checkmark icon in brand color + text), and a full-width CTA button at the bottom.

**Usage progress bars** — animate width from 0 to target value on page load (`transition: width 0.9–1s cubic-bezier(.22,.9,.3,1)`), not instant — this applies both to the sidebar mini widget and the dashboard stat cards.

## Interaction rules

Every interactive surface (nav item, card, button) needs a hover transition — never an instant/no-feedback state change. Keep transitions in the 120–250ms range; nothing longer feels sluggish. Avoid decorative animation that doesn't communicate state (no infinite floating/pulsing elements on core app screens — that's fine for a marketing/landing page only, not the working dashboard).

## What NOT to do

No full-gradient background panels (navbar, hero-style blocks) on the working app screens — gradient is an accent, not a backdrop. No emoji as icons. No mixing serif and sans-serif for functional UI text. No duplicating the same detailed widget across two pages — show a condensed version in one place, full detail in the other.

---

# Landing page (marketing, logged-out)

Reference file: `studymate-landing.html`. This is a separate, public-facing page — not the logged-in app shell. Unlike the app screens, gradient backgrounds and light motion are acceptable here since it's a marketing surface, not a working tool.

## Purpose

The current landing page is just a logo, one line of copy, and a single button — it gives a visitor no idea what the product does. Replace it with a real marketing page that explains the product, shows what it looks like, and states pricing, before asking anyone to sign up.

## Structure (top to bottom)

1. **Nav bar** — logo left; center links to `#features`, `#how`, `#pricing`; right side has a plain text "Sign in" link (routes to `/signin`) and a primary "Get started" button (routes to `/signup`). Sign in and Get started are two different destinations — sign in is for existing accounts, get started always goes to sign-up, never to sign-in.

2. **Hero** — small pill/eyebrow label above the headline (e.g. "AI study assistant"), a headline that states the core value prop in one sentence, one sentence of supporting copy, two CTAs (`Get started free` → `/signup`, and a secondary ghost button `See how it works` that scroll-links to the `#how` section). Below the copy, show a framed product preview — a scaled-down, simplified mockup of the actual dashboard (sidebar + a couple of stat cards) inside a browser-chrome-style card with shadow. This is the single most important addition: visitors need to see the product, not just read about it.

3. **How it works** (`id="how"`) — three numbered steps in a row, each with a circular numbered badge (brand gradient fill), a short title, and one sentence of explanation. For StudyMate specifically: 1) upload your materials, 2) ask a question or generate flashcards/quizzes, 3) get an answer cited back to the source.

4. **Features** (`id="features"`) — a 4-column grid of feature cards, each with a small tinted icon badge (different accent color per card so they're visually distinct: teal, blue, amber, pink), a title, and one sentence of description. Cover: cited answers, auto flashcards, practice quizzes, per-subject organization.

5. **Pricing** (`id="pricing"`) — three plan cards side by side, matching `billing/service.LIMITS`:
   - Free — $0, 3 subjects, 10 documents per subject, 20 generations/day. CTA: ghost button "Get started free" → `/signup`.
   - Pro — $20/month, 50 subjects, 200 documents per subject, 200 generations/day. Featured: 1.5px brand-colored border + "Most popular" pill badge overlapping the top edge. CTA: primary button "Upgrade to Pro" → `/signup?plan=pro`.
   - Business — $100/month, unlimited subjects/documents/generations. CTA: ghost button "Upgrade to Business" → `/signup?plan=business`.
   Each card: tier name, price (large/bold, `/month` in small muted text), one-line description, a checklist of the plan's limits with a checkmark icon, then the CTA button. Passing `?plan=pro` / `?plan=business` as a query param lets the sign-up flow pre-select the chosen tier.

6. **Closing CTA band** — a full-width rounded panel filled with the brand gradient (this is the one place on the whole product where a large gradient fill is appropriate), white text, a short headline ("Ready to study smarter?"), one line ("Start free — no credit card required."), and a single white button linking to `/signup`.

7. **Footer** — minimal: copyright on the left, an "Already have an account? Sign in" link on the right pointing to `/signin`.

## Routing rules (must be exact)

- Every "Get started" / "Get started free" button → `/signup` (never `/signin`).
- The nav "Sign in" link and the footer "Already have an account?" link → `/signin`.
- Pricing card CTAs for Pro/Business append `?plan=pro` or `?plan=business` to the `/signup` link so the plan can be pre-selected on the sign-up form.
- The Free plan's CTA still points to `/signup` with no plan param (or `?plan=free`), not to sign-in.

## Style notes specific to this page

Reuse the same color tokens, spacing scale, and icon rules from the app-shell spec above (teal/emerald brand gradient, 8px spacing, outline SVG icons, no emoji). Differences allowed only on this page: the closing CTA band may use a full gradient fill, and the hero/feature cards may use subtle hover lift transitions for visual interest since this is a persuasion surface, not a daily-use tool.
