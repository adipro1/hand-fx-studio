# Reference Analysis — HAND FX STUDIO

All four reference videos were opened and inspected frame by frame with OpenCV
(contact sheets of 24 evenly spaced frames per video, full-resolution stills, and
dense 3–5 frame-step sequences around key transitions).

| File | Resolution | FPS | Duration | Orientation |
|---|---|---|---|---|
| `refrence_01.mp4` | 360×640 (content letterboxed ~360×230) | 30 | 12.3 s | 9:16 with 16:9 content |
| `refrence_02.mp4` | 960×720 | 30 | 38.8 s | 4:3 |
| `refrence_03.mp4` | 576×720 (top half = output, bottom = TouchDesigner UI) | 30 | 18.5 s | 4:5 screen capture |
| `refrence_04.mp4` | 892×576 (TouchDesigner window capture) | 30 | 10.7 s | 16:9-ish |

---

## Reference 01 — "Glass Prism Frame"

### Visual breakdown
- Dark bedroom scene, the whole image graded **cold blue / violet** with crushed blacks.
- A **quadrilateral window** is held between both hands. Inside it, the image is
  **brightened, desaturated towards a silvery cool white, high contrast** — the face
  looks lit by a lightbox, like seen through a sheet of glass.
- The quad is rendered as a **3D glass slab / prism**: several thin white outlines of the
  quad are drawn at slightly offset positions (time-delayed copies that lag behind the
  hands), and the corners are joined by **triangular facets** that catch **cyan and
  magenta refraction glints**.
- Lines are thin (1–2 px), crisp, white with slight glow.

### Interaction breakdown
- Quad corners follow the **thumb tip and index tip of each hand** (L-shaped "camera
  frame" gesture). Rotating / tilting the hands rotates and skews the slab.
- Moving hands apart enlarges the window; quick movement leaves visible "echo" outlines
  behind (frames 180–213), which is what produces the 3D-prism look.
- The effect is continuous — no on/off triggers visible.

### Effects identified
1. Polygon mask from 4 fingertips.
2. Inside-mask grade: exposure lift, desaturation, cool tint, contrast; slight magnification.
3. Outside grade: darkened, blue tinted.
4. Echo / motion-trail outlines (history of quad vertices).
5. Facet triangles between current quad and echo quads with chromatic glints.

### Implementation technique
- 2D, shader based. Fragment shader does point-in-quad test on the 4 fingertip
  coordinates, applies the inner/outer colour grade and a small refraction offset
  (sample the camera texture slightly scaled about the quad centre, separate offset per
  RGB channel near edges).
- Keep a ring buffer of the last N quad vertex sets (sampled every ~2 frames); draw them
  as thin glowing lines with decreasing alpha; draw translucent facet triangles joining
  corner *i* of the current quad with corners *i* of an older quad, tinted cyan/magenta.
- **Difficulty:** medium.

### Integration in HAND FX STUDIO
Effect **"Glass Prism"** (frame family). Parameters: echo count, echo lag, inner
brightness, tint colour, outside dim, refraction strength, glint colours.

---

## Reference 02 — "Filter Frame" with pinch-to-switch

### Visual breakdown
- Natural warm webcam image, untouched outside the frame.
- Inside a **4-point polygon** between both hands, a strong stylised filter is applied.
  Filters seen over the 38 s:
  1. **Duotone halftone** — blue background, magenta dots sized by luminance (0–8 s).
  2. **Pixelation / mosaic** with large blocks; the outline itself is **stepped along the
     pixel grid** in hot pink (10–18 s).
  3. **Colour inversion** (negative, cyan/blue skin) intermixed with pixelation.
  4. **Cyan halftone on black** — dark triangle with cyan dot screen (20–23 s).
  5. **Magenta halftone on black** (25 s).
  6. **Cyan/magenta halftone** variant (30–32 s).
  7. **Rainbow / "turbo" false-colour heatmap** (33–35 s).
- Outline: thin white (halftone modes) or hot pink (pixel mode), 2–3 px.

### Interaction breakdown
- Polygon vertices = **left index tip, right index tip, right thumb tip, left thumb tip**.
- When one hand is pinched (thumb touches index) the polygon degenerates into a
  **triangle** (frames 600–625) — the effect keeps working with 3 effective points.
- **Mode switch**: the user brings all four fingertips together until the frame
  collapses to a tiny shape (frames 205–255, 540–595, 808–858). When the frame reopens,
  the **next filter** is active. This is a clean, reliable and very satisfying gesture.
- Frame can be any shape — trapezoids, skewed quads, slivers.

### Effects identified
Halftone (dot screen), duotone mapping, pixelation, grid-aligned stepped mask, colour
inversion, false-colour colormaps (jet/turbo), polygon masking, mode cycling.

### Implementation technique
- Single fragment shader with a `mode` uniform; polygon mask via edge-function test;
  halftone via rotated grid cells (dot radius ∝ luminance); pixelation via
  `floor(uv*cells)/cells`; stepped outline by evaluating the mask at the block centre;
  colormaps via polynomial approximations of turbo/jet.
- Mode switch: track the frame area; when it drops below a threshold and then grows again
  → advance mode. Hysteresis + cooldown prevents double triggers.
- **Difficulty:** low–medium. **Highest visual payoff per effort.**

### Integration
Effect **"Filter Frame"** — the flagship effect. Many modes (all of the above plus extras),
pinch-collapse to cycle, outline colour per mode.

---

## Reference 03 — "Finger Bands" (multi-layer strips, TouchDesigner)

### Visual breakdown
- Dark room. Upper half of the capture is the output; bottom half is the TouchDesigner
  network (not part of the effect).
- Between the two hands the image is cut into **horizontal bands**, each band showing a
  different processing of the camera:
  - **Thermal / jet colormap** (deep blue → cyan → yellow → red) — hands and face glow red.
  - **Black band with white edge-detection lines** (sketch-like outline of the face,
    glasses and hands).
  - **Cyan horizontal scanline / glitch noise** on dark navy — data-moshed stripes.
- Band boundaries are straight lines from a fingertip on the left hand to the matching
  fingertip on the right hand.

### Interaction breakdown
- With peace signs (frame 264) the top band is a thin sliver between the **index and
  middle tips** of each hand, while the large band below (middle → thumb) shows edges.
- With wide-open hands (frames 48–120) the bands are stacked from index → thumb.
- Tilting the hands tilts the bands independently, creating wedge shapes. Fingers that
  cross a band are themselves shown in thermal colours (the filter applies to everything
  inside the band, hands included).

### Effects identified
Fingertip-to-fingertip line pairing across hands, multiple stacked polygon bands,
per-band filters (thermal colormap, Sobel edge detection on black, scanline glitch).

### Implementation technique
- For each pair of adjacent fingers (thumb↔index, index↔middle, middle↔ring,
  ring↔pinky) build a quad: `L_tip[f], R_tip[f], R_tip[f+1], L_tip[f+1]`. Shader tests
  each band in order and applies that band's filter.
- Thermal: luminance → jet colormap. Edges: Sobel magnitude on luminance, white on black.
  Scanline glitch: horizontal line pattern modulated by luminance + time-varying row
  offset noise, cyan on navy.
- **Difficulty:** medium.

### Integration
Effect **"Finger Bands"**: bands between matching fingertips; configurable filter per band
(choose from the Filter Frame mode library), band count follows extended fingers.

---

## Reference 04 — "Tracking Skeleton + Masked Region" (TouchDesigner tutorial)

### Visual breakdown
- MediaPipe-style **hand skeleton**: bright **green bones**, **red joint dots** on all
  21 landmarks of both hands.
- **White double-line quad** connecting the two hands (index tips on top, thumb tips
  at the bottom) — thin, slightly offset parallel lines giving a "technical HUD" look.
- Inside / around the region: **mosaic pixelation**, **gaussian blur**, and a **text
  overlay** ("TUTORIAL OUT NOW") clipped to the quad.
- Small floating **label boxes** near the hands (debug-HUD tags).

### Interaction breakdown
- Region follows index/thumb tips of both hands in real time; skeleton drawn on top.
- Region effect switches between pixelate, blur and text over time.

### Effects identified
Skeleton visualisation, inter-hand connection lines, region pixelation, region blur,
masked text.

### Implementation technique
- Skeleton: draw 21 connections as anti-aliased capsules + joint circles (GPU instanced
  SDF primitives).
- Region blur: multi-tap blur inside the polygon mask (in the Filter Frame shader).
- Masked text: render text to a texture (Qt/PIL), sample inside polygon in the shader.
- **Difficulty:** low.

### Integration
Effect **"Hand Skeleton"** (multiple styles, including a faithful "Classic" green/red style
and neon glow styles) and **"Hand Link"** lines; *Blur*, *Pixelate* and *Text* added as
Filter Frame modes.

---

## Common visual language

1. **The hand frame.** Every reference uses fingertips of *both hands* as vertices of a
   live polygon. The region between the hands is a "lens" onto an alternate reality.
   This is the signature interaction and must be the heart of HAND FX STUDIO.
2. **Hard-edged stylised filters**, not soft blending: halftone, pixel mosaic, thermal
   colormaps, edge detection, inversion, duotone. Strong graphic contrast with the
   untouched outside world.
3. **Thin crisp outlines** (white / hot pink / cyan) around regions; technical HUD feel.
4. **Real-time 2D image processing** — all effects are 2D shader effects on the webcam
   texture; no true 3D. The "3D" in ref 01 is faked with time echoes.
5. **Palette:** electric blue, magenta/hot pink, cyan, thermal rainbow, black.
6. **Simple, robust gestures:** L-shaped hands, pinch, open palm. No complicated poses.

## Most distinctive features (ranked)
1. Filter Frame with pinch-collapse mode cycling (ref 02).
2. Finger Bands with stacked per-band filters (ref 03).
3. Glass Prism echoes and facets (ref 01).
4. Skeleton + hand-link HUD (ref 04).

## Prioritised implementation roadmap
| Priority | Item | Source |
|---|---|---|
| P0 | GPU pipeline: camera texture → image passes → overlay canvas → bloom → composite | all |
| P0 | Polygon mask + filter library shader (halftone, duotone, pixelate, invert, thermal, turbo, edges, scanline, blur, posterise, text) | 02, 03, 04 |
| P0 | **Filter Frame** effect with pinch-collapse cycling | 02 |
| P0 | **Hand Skeleton** (Classic, Neon, Minimal) + Hand Link lines | 04 |
| P1 | **Finger Bands** | 03 |
| P1 | **Glass Prism** | 01 |
| P2 | Reality distortion (liquid warp, ripple, swirl, chromatic aberration, kaleidoscope) driven by fingertips | brief |
| P2 | Particles, energy beams/orbs/shockwaves, geometry, portals, colour transforms | brief |
| P3 | Presets combining the above, recording/export, UI polish | brief |

The four references define the application's identity (hand-frame lenses, graphic
filters, thin HUD lines); the additional effects from the brief are designed in the same
visual language so everything layers cohesively.
