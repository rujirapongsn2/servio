---
name: Softnix Servio
description: Servio admin console, styled to the Softnix CI shared with EDC1 (Softnix Data Lakehouse look).
colors:
  primary: "#4582b8"
  primary-hover: "#3e75a6"
  primary-disabled: "#9fbed9"
  primary-tint: "#ecf4fa"
  primary-tint-strong: "#d6e6f3"
  selected-row: "#e0eef7"
  ink: "#101b2a"
  ink-muted: "#566377"
  ink-faint: "#6b7585"
  ink-disabled: "#9aa3b0"
  line: "#e2e5ea"
  line-strong: "#d3d8e0"
  canvas: "#f9fafb"
  topbar: "#fafafb"
  surface: "#ffffff"
  surface-sunken: "#f6f8fa"
  segmented-track: "#eef0f3"
  dark-chip: "#1e273a"
  success: "#3e9f4d"
  success-tint: "#e2fbe8"
  warning: "#d0761f"
  warning-tint: "#fdf1e4"
  danger: "#e74341"
  danger-tint: "#fdeceb"
  softnix-orange: "#f3903f"
  softnix-yellow: "#fdc70c"
  softnix-lime: "#a9cb2e"
typography:
  page-title:
    fontFamily: "Inter, Noto Sans Thai, system-ui, sans-serif"
    fontSize: "26px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  card-title:
    fontFamily: "Inter, Noto Sans Thai, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 600
  body:
    fontFamily: "Inter, Noto Sans Thai, system-ui, sans-serif"
    fontSize: "13.5px"
    fontWeight: 400
    letterSpacing: "-0.003em"
  label:
    fontFamily: "Inter, Noto Sans Thai, system-ui, sans-serif"
    fontSize: "12.5px"
    fontWeight: 500
  dialog-title:
    fontFamily: "Inter, Noto Sans Thai, system-ui, sans-serif"
    fontSize: "22px"
    fontWeight: 500
    letterSpacing: "-0.02em"
  micro:
    fontFamily: "Inter, Noto Sans Thai, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 500
  code:
    fontFamily: "JetBrains Mono, ui-monospace, monospace"
    fontSize: "12px"
rounded:
  sm: "6px"
  md: "8px"
  lg: "12px"
spacing:
  page-x: "28px"
  page-top: "24px"
  card: "18px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    height: "34px"
    padding: "0 14px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    height: "34px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    height: "34px"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    padding: "{spacing.card}"
  nav-item-active:
    backgroundColor: "{colors.primary-tint}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
  badge:
    backgroundColor: "{colors.primary-tint}"
    textColor: "{colors.primary-hover}"
    rounded: "{rounded.sm}"
    height: "21px"
  table-header:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink-muted}"
    typography: "{typography.label}"
---

# Design System: Softnix Servio

## Overview

**Creative North Star: "The Lakehouse Console"**

Servio's admin console shares one CI with EDC1 and the Softnix Data Lakehouse platform: a calm, flat operations tool where one muted Softnix blue marks the action and everything else is navy-tinted grayscale. Density is medium; scanability beats expression. Brand lives in precise details (the logo block, the blue active pill, sentence-case labels), not in decoration.

Reference implementation: EDC1 `src/styles.css` (section "Softnix Data Lakehouse CI alignment") and `docs/ci-lakehouse.md`. When the two disagree, EDC1 wins.

**Key Characteristics:**
- Flat colour, no gradients on UI surfaces; the orange-yellow-lime-blue spectrum stays in the logo and in chart series.
- White sidebar with a right hairline, white cards on a `canvas` page, `topbar` strip with a bottom hairline.
- Sentence case everywhere, including table headers and nav groups.
- Inter for Latin, Noto Sans Thai for Thai, JetBrains Mono only for code and technical values.

## Colors

One accent, navy neutrals, four status hues.

### Primary
- **Lakehouse Blue** (primary): primary buttons, active nav icon, links, focus border, user avatar, the first chart series. Hover deepens to primary-hover; disabled is primary-disabled, never 50% opacity.
- **Blue Mist** (primary-tint): active nav pill, icon tiles, info badges, selected rows lean on selected-row.

### Neutral
- **Ink Navy** (ink): headings, body, nav labels.
- **Slate Muted** (ink-muted): secondary copy, table header labels.
- **Slate Faint** (ink-faint): metadata and placeholders. Darker than EDC1's #7d8796 so small text keeps 4.5:1 on white.
- **Slate Disabled** (ink-disabled): disabled icons, dashed connectors, unknown-state dots. Never for readable text.
- **Hairline** (line) and **Strong Hairline** (line-strong): card/table rules and control borders.
- **Canvas** (canvas), **Top Bar** (topbar), **Sunken** (surface-sunken), **Segmented Track** (segmented-track).

### Status
- success / warning / danger with their tints, as Lakehouse pills (tint background, deep text).
- The Softnix spectrum (softnix-orange, softnix-yellow, softnix-lime) is for charts and the logo only.

**The One Blue Rule.** Every solid action button is primary blue. Green, orange and violet solid buttons are drift.

**The Remapped Ramp Rule.** Tailwind's gray/slate, blue/sky/indigo/violet/purple, green/emerald, red, amber/orange and yellow ramps are re-pointed at this palette in `frontend/src/app/globals.css` (`@theme`). Prefer the semantic utilities (`bg-primary`, `text-ink`, `border-line` …) in new code.

## Typography

**Body Font:** Inter with Noto Sans Thai (system-ui fallback)
**Mono Font:** JetBrains Mono

Inter is pinned by the Softnix CI (EDC1 / Lakehouse), so the detector's "overused font" note is an accepted exception.

**Character:** Neutral, tight and legible in both scripts; hierarchy comes from size and weight, not colour.

### Hierarchy
- **Page title** (700, 26px, 1.2, -0.02em): one per page.
- **Card title** (600, 15px).
- **Body** (400, 13.5px): default UI text.
- **Dialog title** (500, 22px, -0.02em): modal headings.
- **Label** (500, 12.5px): table headers, field labels; sentence case, no letter-spacing.
- **Micro** (500, 11px): badges, counters, meta. Nothing in the UI goes below 11px.

## Layout

Fixed 256px sidebar (64px collapsed rail), 56px top bar, page padding 24px top / 28px sides. Cards sit on the canvas with 16–24px gaps.

## Elevation & Depth

Flat by default: hairline borders carry structure, with a 1–2px soft shadow (`0 1px 2px rgba(16,27,42,.04)`) on cards. Popovers and modals use `0 12px 32px rgba(16,27,42,.12)`.

## Shapes

Controls (buttons, inputs, badges, chips, nav items) 6px. Cards and modals 12px. Avatars round.

## Components

### Buttons
- **Shape:** 6px, 34px tall (28px small).
- **Primary:** solid blue, white text; hover primary-hover; disabled primary-disabled.
- **Secondary:** white with line-strong border; hover fill `#f3f5f8`.
- **Focus:** primary border + 3px primary-tint-strong ring.

### Inputs / Fields
- 34–40px tall, 6px radius, line-strong border, white fill. Focus: primary border + 3px primary-tint ring.

### Navigation
- White sidebar; brand block is the Softnix logo with the product name ("Servio") under it, the Softnix mark when collapsed.
- Items 13.5px, 6px radius; hover `#f3f5f8`; active = primary-tint pill, semibold ink label, blue icon.

### Tabs
- Segmented: segmented-track background, white active pill with a 1px soft shadow, 13px labels.

### Tables
- Header row on canvas, label typography in ink-muted, sentence case; row rules `#eceef2`; no vertical rules. Hover row `#f6f9fc`.

### Badges
- 6px radius, tint background + deep text of the same hue; 11–12px, weight 500.

## Do's and Don'ts

### Do:
- **Do** use `bg-primary` for the single primary action in a view.
- **Do** keep table headers and nav labels in sentence case.
- **Do** use the Softnix spectrum colours for chart series in order: blue, lime, orange, yellow.

### Don't:
- **Don't** add gradients, glass or coloured side-stripes to cards.
- **Don't** introduce violet/indigo accents; they map to the primary blue.
- **Don't** use uppercase tracked labels for table headers.
