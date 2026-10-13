---
name: anatomy
description: Internal Sergio design skill. Apply to every visual creation, interface, Node character, hologram and technical illustration; use precise physical geometry and the bundled Anatomy kit for interactive explanations.
license: MIT
metadata:
  openjarvis:
    user_invocable: false
---

# Anatomy para Sergio

This is an internal craft guide, never a navigation section. Apply its design
principles whenever Sergio makes a visual result. Do not mention skill execution
in the product UI. Preserve the user's typography, accessibility and established
components instead of producing a new generic dashboard.

## Always-on design principles

- Start from the existing layout and the real user's task. Black, white and one
  pale-blue interactive accent; restrained spacing and readable type.
- Prefer existing open-source professional applications over miniature replicas:
  FreeCAD / Bonsai / LibreCAD for architecture, ArtCraft apps for creative work,
  Kdenlive for video, OpenDesign for canvas layouts and VSCodium for development.
- Characters must feel friendly: rounded silhouettes, small expressive eyes,
  soft felt, grounded shadows. Make original characters; retain user choices.
- Show real state. Never animate completion or label an integration installed
  without evidence. Never describe webcam recognition as hardware authentication.
- Respect reduced motion, keyboard navigation, focus, contrast and phone layouts.

## Detailed interactive illustrations

Read `references/upstream-skill.md`, then choose the closest source example in
`examples/`. Follow its truth-first workflow, parts list, physical supports,
depth sorting and screenshot checks. Use `kit/iso-kit.ts` or `.mjs` for projection
and filled solids; `kit/lathe.mjs` and `kit/tube.mjs` for round parts and cables.
Precompute geometry. Animate transforms on refs, pause when offscreen, and avoid
React state updates per frame. Every readout must come from the actual model.

Use `references/craft.md`, `references/motion.md` and `references/verify.md` while
building. Run the bundled geometry audit and line checks when applicable. Inspect
desktop, 390px phone, light/dark and detail captures before calling it finished.
For native holograms, preserve materials and dimensions; add stable light,
contact shadows and quiet reflections without full-frame blur per animation tick.

## Source and boundaries

Adapted from Ryan's Anatomy, MIT, pinned upstream commit
`240a9bf7c50cc6226148762a1017466fcbc08523` at
https://github.com/wheresryan22/anatomy. Original kit, references, examples,
scripts and license remain bundled. Generated example pages and media are omitted.
This adaptation does not grant access to a proprietary product or claim identical
performance. Use source licenses and separate tools honestly.
