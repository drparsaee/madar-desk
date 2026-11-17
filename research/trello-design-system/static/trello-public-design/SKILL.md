---
name: Trello-Public-design
description: Design system skill for Trello-Public. Activate when building UI components, pages, or any visual elements. Provides exact color tokens, typography scale, spacing grid, component patterns, and craft rules. Read references/DESIGN.md before writing any CSS or JSX.
---

# Trello-Public Design System

You are building UI for **Trello-Public**. Light-themed, neutral palette, sans-serif typography (Charlie Text), compact density on a 4px grid, expressive motion.

## Visual Reference

**IMPORTANT**: Study ALL screenshots below before writing any UI. Match colors, typography, spacing, layout, and motion exactly as shown.

### Homepage

![Trello-Public Homepage](screenshots/homepage.png)

> Read `references/DESIGN.md` for full token details.

## Design Philosophy

- **Layered depth** — use shadow tokens to create a sense of physical layering. Each elevation level has a specific shadow.
- **Gradient accents** — gradients are used thoughtfully for emphasis, not decoration.
- **Type pairing** — Charlie Text for body/UI text, Charlie Display for headings/display. Never introduce a third typeface.
- **compact density** — 4px base grid. Every dimension is a multiple of 4.
- **neutral palette** — the color temperature runs neutral, matching the sans-serif typography.
- **Restrained accent** — `#eae6ff` is the only pop of color. Used exclusively for CTAs, links, focus rings, and active states.
- **Expressive motion** — animations are an integral part of the experience. Use spring physics and layout animations.

## Color System

### Core Palette

| Role | Token | Hex | Use |
|------|-------|-----|-----|
| Background | `--background` | `#ffffff` | Page/app background |
| Text Primary | `--text-primary` | `#172b4d` | Headings, body text |
| Text Muted | `--text-muted` | `#505258` | Captions, placeholders |
| Accent | `--accent` | `#eae6ff` | CTAs, links, focus rings |

### Extended Palette

- `#091e42`
- **ds-text-selected:** `#1868db`
- **ds-text-accent-blue-bolder:** `#123263`
- **ds-border:** `#0b120e` — Deep background layer or shadow color
- `#505f79`
- **ds-text-disabled:** `#080f21` — Deep background layer or shadow color
- `#0747a6`
- **ds-text-accent-blue:** `#1558bc`

### CSS Variable Tokens

```css
--ds-text-accent-lime: #4C6B1F;
--ds-text-accent-lime-bolder: #37471F;
--ds-text-accent-red: #AE2E24;
--ds-text-accent-red-bolder: #5D1F1A;
--ds-text-accent-orange: #9E4C00;
--ds-text-accent-orange-bolder: #693200;
--ds-text-accent-yellow: #7F5F01;
--ds-text-accent-yellow-bolder: #533F04;
--ds-text-accent-green: #216E4E;
--ds-text-accent-green-bolder: #164B35;
--ds-text-accent-teal: #206A83;
--ds-text-accent-teal-bolder: #164555;
--ds-text-accent-blue: #1558BC;
--ds-text-accent-blue-bolder: #123263;
--ds-text-accent-purple: #803FA5;
--ds-text-accent-purple-bolder: #48245D;
--ds-text-accent-magenta: #943D73;
--ds-text-accent-magenta-bolder: #50253F;
--ds-text-accent-gray: #505258;
--ds-text-accent-gray-bolder: #1E1F21;
```

## Typography

### Font Stack

- **Charlie Text** — Heading 1, Heading 2, Heading 3
- **Charlie Display** — Body, Caption
- **SFMono-Medium** — Code

### Font Sources

```css
@font-face {
  font-family: "Charlie Display";
  src: url("fonts/CharlieDisplay-Regular.ttf") format("woff2");
  font-weight: 400;
}
@font-face {
  font-family: "Charlie Display";
  src: url("fonts/CharlieDisplay-700.ttf") format("woff2");
  font-weight: 700;
}
@font-face {
  font-family: "Charlie Text";
  src: url("fonts/CharlieText-Regular.ttf") format("woff2");
  font-weight: 400;
}
@font-face {
  font-family: "Charlie Text";
  src: url("fonts/CharlieText-700.ttf") format("woff2");
  font-weight: 700;
}
```

### Type Scale

| Role | Family | Size | Weight |
|------|--------|------|--------|
| Heading 1 | Charlie Text | 6.5rem | 700 |
| Heading 2 | Charlie Text | 5.5rem | 700 |
| Heading 3 | Charlie Text | 3rem | 700 |
| Body | Charlie Display | 1rem | 400 |
| Caption | Charlie Display | 0.75rem | 400 |
| Code | SFMono-Medium | 14px | 400 |

### Typography Rules

- Body/UI: **Charlie Text**, Headings: **Charlie Display** — these are the only display fonts
- Max 3-4 font sizes per screen
- Headings: weight 600-700, body: weight 400
- Use color and opacity for text hierarchy, not additional font sizes
- Line height: 1.5 for body, 1.2 for headings

## Spacing & Layout

### Base Grid: 4px

Every dimension (margin, padding, gap, width, height) must be a multiple of **4px**.

### Spacing Scale

`2, 4, 6, 8, 10, 12, 16, 20, 24, 28, 32, 40` px

### Spacing as Meaning

| Spacing | Use |
|---------|-----|
| 4-8px | Tight: related items (icon + label, avatar + name) |
| 12-16px | Medium: between groups within a section |
| 24-32px | Wide: between distinct sections |
| 48px+ | Vast: major page section breaks |

### Border Radius

Scale: `0.2rem, 0.25rem, 0.3rem, 0.5rem, .75rem, 3px, 4px, 6px, 9pt, 20px, 22px, inherit`
Default: `4px`

### Container

Max-width: `992px`, centered with auto margins.

### Breakpoints

| Name | Value |
|------|-------|
| xs | 0px |
| sm | 575px |
| sm | 576px |
| md | 767px |
| md | 767.98px |
| md | 768px |
| lg | 991px |
| lg | 991.98px |
| lg | 992px |
| xl | 1199px |
| xl | 1200px |
| 2xl | 1400px |

Mobile-first: design for small screens, layer on responsive overrides.

## Component Patterns

### Card

```css
.card {
  background: #ffffff;
  border-radius: 4px;
  padding: 16px;
  box-shadow: 0 8px 9pt #091e4226,0 0 1px #091e424f;
}
```

```html
<div class="card">
  <h3>Card Title</h3>
  <p>Card content goes here.</p>
</div>
```

### Button

```css
/* Primary */
.btn-primary {
  background: #eae6ff;
  color: #172b4d;
  border-radius: 4px;
  padding: 8px 16px;
  font-weight: 500;
  transition: opacity 150ms ease;
}
.btn-primary:hover { opacity: 0.9; }

/* Ghost */
.btn-ghost {
  background: transparent;
  border: 1px solid #cccccc;
  color: #172b4d;
  border-radius: 4px;
  padding: 8px 16px;
}
```

```html
<button class="btn-primary">Get Started</button>
<button class="btn-ghost">Learn More</button>
```

### Input

```css
.input {
  background: #ffffff;
  border: 1px solid #cccccc;
  border-radius: 4px;
  padding: 8px 12px;
  color: #172b4d;
  font-size: 14px;
}
.input:focus { border-color: #eae6ff; outline: none; }
```

```html
<input class="input" type="text" placeholder="Search..." />
```

### Badge / Chip

```css
.badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 8px;
  border-radius: 9999px;
  font-size: 12px;
  font-weight: 500;
  background: #ffffff;
  color: #505258;
}
```

```html
<span class="badge">New</span>
<span class="badge">Beta</span>
```

### Modal / Dialog

```css
.modal-backdrop { background: rgba(0, 0, 0, 0.6); }
.modal {
  background: #ffffff;
  border-radius: inherit;
  padding: 24px;
  max-width: 480px;
  width: 90vw;
  box-shadow: inset 60px 0#32cd3266,inset -60px 0#32cd3266;
}
```

```html
<div class="modal-backdrop">
  <div class="modal">
    <h2>Dialog Title</h2>
    <p>Dialog content.</p>
    <button class="btn-primary">Confirm</button>
    <button class="btn-ghost">Cancel</button>
  </div>
</div>
```

### Table

```css
.table { width: 100%; border-collapse: collapse; }
.table th {
  text-align: left;
  padding: 8px 12px;
  font-weight: 500;
  font-size: 12px;
  color: #505258;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid #cccccc;
}
.table td {
  padding: 12px;
  border-bottom: 1px solid #cccccc;
}
```

```html
<table class="table">
  <thead><tr><th>Name</th><th>Status</th><th>Date</th></tr></thead>
  <tbody>
    <tr><td>Item One</td><td>Active</td><td>Jan 1</td></tr>
    <tr><td>Item Two</td><td>Pending</td><td>Jan 2</td></tr>
  </tbody>
</table>
```

### Navigation

```css
.nav {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
}
.nav-link {
  color: #505258;
  padding: 8px 12px;
  border-radius: 4px;
  transition: color 150ms;
}
.nav-link:hover { color: #172b4d; }
.nav-link.active { color: #eae6ff; }
```

```html
<nav class="nav">
  <a href="/" class="nav-link active">Home</a>
  <a href="/about" class="nav-link">About</a>
  <a href="/pricing" class="nav-link">Pricing</a>
  <button class="btn-primary" style="margin-left: auto">Get Started</button>
</nav>
```

### Extracted Components

These components were found in the codebase:

**Button** (`html`)

**Navigation** (`html`)

## Page Structure

The following page sections were detected:

- **Navigation** — Top navigation bar (7 items)
- **Hero** — Hero section (detected from heading structure)
- **Faq** — FAQ/accordion section
- **Footer** — Page footer with links and info (13 items)
- **Cta** — Call-to-action section

When building pages, follow this section order and structure.

## Animation & Motion

This project uses **expressive motion**. Animations are part of the design language.

### CSS Animations

- `wac-fade-in`
- `wac-fade-up`
- `wac-fade-out`
- `wac-scale-in`
- `wac-scale-out`

### Motion Tokens

- **Duration scale:** `0ms`, `.1s`, `.175s`, `.35s`, `.7s`, `.86s`, `1s`, `2s`, `50ms`, `100ms`, `150ms`, `200ms`, `250ms`, `300ms`, `600ms`
- **Easing functions:** `ease-out`, `cubic-bezier(.6,0,0,1)`, `cubic-bezier(.15,1,.3,1)`, `cubic-bezier(.8,0,0,.8)`, `cubic-bezier(.4,0,0,1)`, `cubic-bezier(.8,0,0,1)`, `cubic-bezier(.2,0,0,1)`, `linear`, `ease-in-out`, `cubic-bezier(.4,.15,.6,.85)`, `ease`

### Motion Guidelines

- **Duration:** Use values from the duration scale above. Short (0ms) for micro-interactions, long (600ms) for page transitions
- **Easing:** Use `ease-out` as the default easing curve
- **Direction:** Elements enter from bottom/right, exit to top/left
- **Reduced motion:** Always respect `prefers-reduced-motion` — disable animations when set

## Depth & Elevation

### Shadow Tokens

- Subtle: `0 2px var(--_184g9oo)`
- Subtle: `0 2px var(--_1isx3d2)`
- Subtle: `1px 0px 0px 0px rgba(255,255,255,1)`
- Raised (cards, buttons): `0 8px 9pt #091e4226,0 0 1px #091e424f`
- Raised (cards, buttons): `unset`
- Raised (cards, buttons): `inset 2pc 0#32cd3266,inset -2pc 0#32cd3266`

### Z-Index Scale

`1, 2, 90, 100, 500, 1000, 99999`

Use these exact values — never invent z-index values.

## Anti-Patterns (Never Do)

- **No blur effects** — no backdrop-blur, no filter: blur()
- **No zebra striping** — tables and lists use borders for separation
- **No invented colors** — every hex value must come from the palette above
- **No arbitrary spacing** — every dimension is a multiple of 4px
- **No extra fonts** — only Charlie Text and Charlie Display and SFMono-Medium are allowed
- **No arbitrary border-radius** — use the scale: 0.2rem, 0.25rem, 0.3rem, 0.5rem, .75rem, 3px, 4px, 6px, 20px, 22px
- **No opacity for disabled states** — use muted colors instead

## Workflow

1. **Read** `references/DESIGN.md` before writing any UI code
2. **Pick colors** from the Color System section — never invent new ones
3. **Set typography** — Charlie Text, Charlie Display, SFMono-Medium only, using the type scale
4. **Build layout** on the 4px grid — check every margin, padding, gap
5. **Match components** to patterns above before creating new ones
6. **Apply elevation** — use shadow tokens
7. **Validate** — every value traces back to a design token. No magic numbers.

## Brand Spec

- **Favicon:** `https://www.trello.com/favicon.ico`
- **Site URL:** `https://trello.com`
- **Brand color:** `#eae6ff`
- **Brand typeface:** Charlie Text

## Quick Reference

```
Background:     #ffffff
Surface:        (not extracted)
Text:           #172b4d / #505258
Accent:         #eae6ff
Border:         (not extracted)
Font:           Charlie Text
Spacing:        4px grid
Radius:         4px
Components:     7 detected
```

## When to Trigger

Activate this skill when:
- Creating new components, pages, or visual elements for Trello-Public
- Writing CSS, Tailwind classes, styled-components, or inline styles
- Building page layouts, templates, or responsive designs
- Reviewing UI code for design consistency
- The user mentions "Trello-Public" design, style, UI, or theme
- Generating mockups, wireframes, or visual prototypes

---

# Full Reference Files

> Every output file is embedded below. Claude has full design system context from /skills alone.

## Design System Tokens (DESIGN.md)

# Trello-Public DESIGN.md

> Auto-generated design system — reverse-engineered via static analysis by skillui.
> Frameworks: None detected
> Colors: 20 · Fonts: 3 · Components: 7
> Icon library: not detected · State: not detected
> Primary theme: light · Dark mode toggle: no · Motion: expressive

## Visual Reference

**Match this design exactly** — study colors, fonts, spacing, and component shapes before writing any UI code.

![Trello-Public Homepage](../screenshots/homepage.png)

---

## 1. Visual Theme & Atmosphere

This is a **light-themed** interface with a neutral, approachable feel. The light background emphasizes content clarity. Typography pairs **Charlie Display** for display/headings with **Charlie Text** for body text, creating clear visual hierarchy through type contrast. Spacing follows a **4px base grid** (compact density), with scale: 2, 4, 6, 8, 10, 12, 16, 20px. The accent color **#eae6ff** anchors interactive elements (buttons, links, focus rings). Motion is expressive — spring physics, layout animations, and staggered reveals are part of the visual language.

---

## 2. Color Palette & Roles

| Token | Hex | Role | Use |
|---|---|---|---|
| ds-text-inverse | `#ffffff` | background | Page background, darkest surface |
| ds-background-brand-boldest | `#172b4d` | text-primary | Headings and body text |
| ds-text-accent-gray | `#505258` | text-muted | Captions, placeholders, secondary info |
| ds-background-accent-blue-subtlest | `#eae6ff` | accent | CTAs, links, focus rings, active states |
| ds-background-accent-gray-subtlest-hovered | `#dfe1e6` | accent | CTAs, links, focus rings, active states |
| ds-background-accent-purple-subtlest | `#f4f5f7` | accent | CTAs, links, focus rings, active states |
| accent | `#0052cc` | accent | CTAs, links, focus rings, active states |
| ds-background-accent-orange-subtlest | `#fff5db` | accent | CTAs, links, focus rings, active states |
| ds-background-accent-red-subtlest-hovered | `#ffd5d2` | accent | CTAs, links, focus rings, active states |
| ds-background-accent-teal-subtlest-hovered | `#c6edfb` | accent | CTAs, links, focus rings, active states |
| ds-icon-accent-blue | `#357de8` | accent | CTAs, links, focus rings, active states |
| ds-background-accent-blue-subtler-pressed | `#8fb8f6` | accent | CTAs, links, focus rings, active states |
| info | `#091e42` | info | Informational highlights |
| ds-text-selected | `#1868db` | unknown | Palette color |
| ds-text-accent-blue-bolder | `#123263` | unknown | Palette color |
| ds-border | `#0b120e` | unknown | Palette color |
| unknown | `#505f79` | unknown | Palette color |
| ds-text-disabled | `#080f21` | unknown | Palette color |
| unknown | `#0747a6` | unknown | Palette color |
| ds-text-accent-blue | `#1558bc` | unknown | Palette color |

### CSS Variable Tokens

```css
--ds-text-accent-lime: #4C6B1F;
--ds-text-accent-lime-bolder: #37471F;
--ds-text-accent-red: #AE2E24;
--ds-text-accent-red-bolder: #5D1F1A;
--ds-text-accent-orange: #9E4C00;
--ds-text-accent-orange-bolder: #693200;
--ds-text-accent-yellow: #7F5F01;
--ds-text-accent-yellow-bolder: #533F04;
--ds-text-accent-green: #216E4E;
--ds-text-accent-green-bolder: #164B35;
--ds-text-accent-teal: #206A83;
--ds-text-accent-teal-bolder: #164555;
--ds-text-accent-blue: #1558BC;
--ds-text-accent-blue-bolder: #123263;
--ds-text-accent-purple: #803FA5;
--ds-text-accent-purple-bolder: #48245D;
--ds-text-accent-magenta: #943D73;
--ds-text-accent-magenta-bolder: #50253F;
--ds-text-accent-gray: #505258;
--ds-text-accent-gray-bolder: #1E1F21;
```


---

## 3. Typography Rules

**Font Stack:**
- **Charlie Text** — Heading 1, Heading 2, Heading 3
- **Charlie Display** — Body, Caption
- **SFMono-Medium** — Code

**Font Sources:**

```css
@font-face {
  font-family: "Charlie Display";
  src: url("fonts/CharlieDisplay-Regular.ttf") format("woff2");
  font-weight: 400;
}
@font-face {
  font-family: "Charlie Display";
  src: url("fonts/CharlieDisplay-700.ttf") format("woff2");
  font-weight: 700;
}
@font-face {
  font-family: "Charlie Text";
  src: url("fonts/CharlieText-Regular.ttf") format("woff2");
  font-weight: 400;
}
@font-face {
  font-family: "Charlie Text";
  src: url("fonts/CharlieText-700.ttf") format("woff2");
  font-weight: 700;
}
```

| Role | Font | Size | Weight |
|---|---|---|---|
| Heading 1 | Charlie Text | 6.5rem | 700 |
| Heading 2 | Charlie Text | 5.5rem | 700 |
| Heading 3 | Charlie Text | 3rem | 700 |
| Body | Charlie Display | 1rem | 400 |
| Caption | Charlie Display | 0.75rem | 400 |
| Code | SFMono-Medium | 14px | 400 |

**Typographic Rules:**
- Limit to 3 font families max per screen
- Use **Charlie Text** for body/UI text, **Charlie Display** for display/headings
- Maintain consistent hierarchy: no more than 3-4 font sizes per screen
- Headings use bold (600-700), body uses regular (400)
- Line height: 1.5 for body text, 1.2 for headings
- Use color and opacity for secondary hierarchy, not additional font sizes


---

## 4. Component Stylings

### Layout (1)

**Footer** — `html`

### Navigation (1)

**Navigation** — `html`

### Data Display (1)

**List** — `html`

### Data Input (2)

**Button** — `html`
- Animation: 

**Input** — `html`
- State: :focus, :placeholder

### Media (2)

**Image** — `html`

**Icon** — `html`



---

## 5. Layout Principles

- **Base spacing unit:** 4px
- **Spacing scale:** 2, 4, 6, 8, 10, 12, 16, 20, 24, 28, 32, 40
- **Border radius:** 0.2rem, 0.25rem, 0.3rem, 0.5rem, .75rem, 3px, 4px, 6px, 9pt, 20px, 22px, inherit
- **Max content width:** 992px

**Spacing as Meaning:**
| Spacing | Use |
|---|---|
| 4-8px | Tight: related items within a group |
| 12-16px | Medium: between groups |
| 24-32px | Wide: between sections |
| 48px+ | Vast: major section breaks |


---

## 6. Depth & Elevation

### Flat — subtle depth hints

- `0 2px var(--_184g9oo)`
- `0 2px var(--_1isx3d2)`
- `1px 0px 0px 0px rgba(255,255,255,1)`

### Raised — cards, buttons, interactive elements

- `0 8px 9pt #091e4226,0 0 1px #091e424f`
- `unset`
- `inset 2pc 0#32cd3266,inset -2pc 0#32cd3266`

### Overlay — full-screen overlays, top-level dialogs

- `inset 60px 0#32cd3266,inset -60px 0#32cd3266`

### Z-Index Scale

`1, 2, 90, 100, 500, 1000, 99999`



---

## 7. Animation & Motion

This project uses **expressive motion**. Animations are an integral part of the experience.

### CSS Animations

- `@keyframes wac-fade-in`
- `@keyframes wac-fade-up`
- `@keyframes wac-fade-out`
- `@keyframes wac-scale-in`
- `@keyframes wac-scale-out`
- `@keyframes wac-slide-in-top`
- `@keyframes wac-slide-in-bottom`
- `@keyframes wac-slide-in-left`

### Animated Components

- **Button**: 

### Motion Guidelines

- Duration: 150-300ms for micro-interactions, 300-500ms for page transitions
- Easing: `ease-out` for enters, `ease-in` for exits
- Always respect `prefers-reduced-motion`


---

## 8. Do's and Don'ts

### Do's

- Use `#eae6ff` for interactive elements (buttons, links, focus rings)
- Use `#ffffff` as the primary page background
- Pair **Charlie Text** (body) with **Charlie Display** (display) — these are the only allowed fonts
- Follow the **4px** spacing grid for all margins, padding, and gaps
- Use the defined shadow tokens for elevation — see Section 6
- Use border-radius from the scale: 0.2rem, 0.25rem, 0.3rem, 0.5rem, .75rem
- Reuse existing components from Section 4 before creating new ones

### Don'ts

- Don't introduce colors outside this palette — extend the design tokens first
- Don't introduce additional font families beyond Charlie Text and Charlie Display and SFMono-Medium
- Don't use arbitrary spacing values — stick to multiples of 4px
- Don't create custom box-shadow values outside the system tokens
- Don't use arbitrary border-radius values — pick from the defined scale
- Don't duplicate component patterns — check Section 4 first
- Don't use backdrop-blur or blur effects

### Anti-Patterns (detected from codebase)

- No blur or backdrop-blur effects
- No zebra striping on tables/lists


---

## 9. Responsive Behavior

| Name | Value | Source |
|---|---|---|
| xs | 0px | css |
| sm | 575px | css |
| sm | 576px | css |
| md | 767px | css |
| md | 767.98px | css |
| md | 768px | css |
| lg | 991px | css |
| lg | 991.98px | css |
| lg | 992px | css |
| xl | 1199px | css |
| xl | 1200px | css |
| 2xl | 1400px | css |

**Approach:** Use `@media (min-width: ...)` queries matching the breakpoints above.


---

## 10. Agent Prompt Guide

Use these as starting points when building new UI:

### Build a Card

```
Background: #ffffff
Border: 1px solid var(--border)
Radius: 4px
Padding: 16px
Font: Charlie Text
Use shadow tokens from Section 6.
```

### Build a Button

```
Primary: bg #eae6ff, text white
Ghost: bg transparent, border var(--border)
Padding: 8px 16px
Radius: 4px
Hover: opacity 0.9 or lighter shade
Focus: ring with #eae6ff
```

### Build a Page Layout

```
Background: #ffffff
Max-width: 992px, centered
Grid: 4px base
Responsive: mobile-first, breakpoints from Section 9
```

### Build a Stats Card

```
Surface: #ffffff
Label: #505258 (muted, 12px, uppercase)
Value: #172b4d (primary, 24-32px, bold)
Status: use success/warning/danger from Section 2
```

### Build a Form

```
Input bg: #ffffff
Input border: 1px solid var(--border)
Focus: border-color #eae6ff
Label: #505258 12px
Spacing: 16px between fields
Radius: 4px
```

### General Component

```
1. Read DESIGN.md Sections 2-6 for tokens
2. Colors: only from palette
3. Font: Charlie Text, type scale from Section 3
4. Spacing: 4px grid
5. Components: match patterns from Section 4
6. Elevation: shadow tokens
```

## Bundled Fonts (fonts/)

The following font files are bundled in the `fonts/` directory:

- `fonts/CharlieDisplay-100.ttf`
- `fonts/CharlieDisplay-100.woff`
- `fonts/CharlieDisplay-100.woff2`
- `fonts/CharlieDisplay-200.ttf`
- `fonts/CharlieDisplay-200.woff`
- `fonts/CharlieDisplay-200.woff2`
- `fonts/CharlieDisplay-500.ttf`
- `fonts/CharlieDisplay-500.woff`
- `fonts/CharlieDisplay-500.woff2`
- `fonts/CharlieDisplay-700.ttf`
- `fonts/CharlieDisplay-700.woff`
- `fonts/CharlieDisplay-700.woff2`
- `fonts/CharlieDisplay-800.ttf`
- `fonts/CharlieDisplay-800.woff`
- `fonts/CharlieDisplay-800.woff2`
- `fonts/CharlieDisplay-900.ttf`
- `fonts/CharlieDisplay-900.woff`
- `fonts/CharlieDisplay-900.woff2`
- `fonts/CharlieDisplay-Regular.ttf`
- `fonts/CharlieDisplay-Regular.woff`
- `fonts/CharlieDisplay-Regular.woff2`
- `fonts/CharlieText-100.ttf`
- `fonts/CharlieText-100.woff`
- `fonts/CharlieText-100.woff2`
- `fonts/CharlieText-200.ttf`
- `fonts/CharlieText-200.woff`
- `fonts/CharlieText-200.woff2`
- `fonts/CharlieText-500.ttf`
- `fonts/CharlieText-500.woff`
- `fonts/CharlieText-500.woff2`
- `fonts/CharlieText-700.ttf`
- `fonts/CharlieText-700.woff`
- `fonts/CharlieText-700.woff2`
- `fonts/CharlieText-800.ttf`
- `fonts/CharlieText-800.woff`
- `fonts/CharlieText-800.woff2`
- `fonts/CharlieText-Regular.ttf`
- `fonts/CharlieText-Regular.woff`
- `fonts/CharlieText-Regular.woff2`

Use these local font files in `@font-face` declarations instead of fetching from Google Fonts.

## Homepage Screenshots (screenshots/)

![homepage.png](screenshots/homepage.png)

