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
  src: url("https://dam-cdn.atl.orangelogic.com/CDNLink/AT12FC6") format("woff2");
  font-weight: 400;
}
@font-face {
  font-family: "Charlie Display";
  src: url("https://dam-cdn.atl.orangelogic.com/CDNLink/AT12FH6") format("woff2");
  font-weight: 700;
}
@font-face {
  font-family: "Charlie Text";
  src: url("https://dam-cdn.atl.orangelogic.com/CDNLink/AT12FKT") format("woff2");
  font-weight: 400;
}
@font-face {
  font-family: "Charlie Text";
  src: url("https://dam-cdn.atl.orangelogic.com/CDNLink/AT12FIA") format("woff2");
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
