# Sergio — Professional Video Editor Powered by AI

**Sergio** is an AI-powered professional video editing studio. Not just an editor: a director, colorist, camera operator, VFX compositor, and production assistant that learns from you with every project.

> *"The only app that edits your videos like a Hollywood professional, but in your language and on your machine."*

---

## What Does Sergio Do?

### 1. Conversational AI Video Editor
- **Import any format**: MP4, MOV, AVI, ProRes, RED, BRAW, MXF
- **Non-destructive editing**: layers, masks, keyframes, nodes
- **Smart cutting**: Sergio detects scenes, silences, repetitions and suggests the best takes
- **Edit by intention**: *"Make this 20-minute vlog have the dynamic pace of a Netflix documentary, use subtle synthwave music on transitions, and highlight moments where I laugh"*
- **Re-framing & physical re-lighting**: The AI reconstructs the scene in 3D. Move the "virtual camera" after recording, change a cloudy day to realistic golden hour, or correct eye contact toward the lens

### 2. Video Boost Ultra (IMAX-Level)
- **Upscale to 4K/8K** with neural super-resolution and lanczos scaling
- **Frame interpolation** (24 to 60/120fps) without artifacts using optical flow
- **NLMeans noise reduction** preserving micro-textures (skin, fabrics, foliage)
- **Temporal HDR**: recovers details in blown highlights and lifts deep shadows
- **Zone-adaptive color grading**: neutralizes tungsten lights without cooling skin tones
- **Gimbal-level stabilization**: eliminates micro-vibrations and walking steps
- **Optical sharpness without oversharpening**: simulates cinema prime lens
- **Complete IMAX pipeline**: result looks shot on Full Frame camera, NEVER like a phone

### 3. Creative Studio (VFX & Motion Graphics)
- **AI video generation**: text-to-video, image-to-video, style transfer
- **Advanced VFX**: particles, fluid simulation, destruction, smoke/fire, cloth simulation
- **Motion graphics**: animated titles, lower thirds, cinematic transitions
- **Professional chroma key** with AI-powered edge refinement
- **Multi-layer compositing** with blending modes and motion tracking
- **Direct pipeline to Blender**: export projects with one click
- **3D holograms** manipulable with bare hands (no gloves)

### 4. Predictive Trend Radar
- **Micro-trend detection**: analyzes TikTok, Reels, Shorts, X, Pinterest, Google Trends and forums to detect audio, formats and themes rising BEFORE they explode
- **Cultural translation**: takes a global trend and proposes how to adapt it to your audience, tone and sector
- **Predictive retention analysis**: simulates how your audience will react second-by-second, marking in RED the points where people will likely swipe away

### 5. Human Thought (Human Analysis, Not Algorithmic)
- Uses the **fly brain (connectome)** to simulate real emotions
- Answers: *"Why does something go viral and something else doesn't?"*
- Detects the **emotional x-factor** that algorithms can't see
- Analyzes your history: what worked, what didn't, why
- Extracts your **unique creative DNA**: your superpower, your kryptonite, your audience's secret desire

### 6. Professional Voiceover & Neural Dubbing
- **Local voice cloning** with 30 seconds of sample audio (Kokoro, free)
- **Premium voice** with ElevenLabs (with your included API)
- **Automatic lip-sync** in any language
- **Neural dubbing**: translates and dubs videos while preserving original timbre
- **Automatic sound design**: detects on-screen movements and places subtle SFX, mixes music ducking voice frequencies

### 7. Smart Multiplatform Workflow
- **Automatic versioning**: from a 16:9 video extracts optimized 9:16 clips for each platform
- **Hook rewriting**: faster and more visual for TikTok, more contextual for Shorts, more professional for LinkedIn
- **A/B Testing**: generates 5 thumbnails and 3 different openings, lets the winner stay based on real click and retention data

### 8. Smart Cross-Device Search
- Find photos, videos and clips on your computer, phone, cloud and social media
- **Visual content search**: *"the clip where the dog is running"*
- **Automatic organization** by scenes, faces, objects and emotions
- **Bidirectional sync** between all your devices

### 9. Automated Publishing
- Export in any format: YouTube, Instagram, TikTok, cinema (DCP)
- **Platform optimization**: Sergio adjusts duration, format, subtitles and hashtags
- Scheduled publishing
- Post-publish metrics analysis

---

## Internal Engine: Terry (Supreme Prompt Engineer)

Terry is not a simple prompt preparer. He is an **elite prompt engineer** using:
- **Chain-of-Thought**: step-by-step reasoning
- **Tree-of-Thoughts**: explores multiple hypotheses before choosing
- **Structural delimiters**: XML, Markdown, triple blocks
- **Negative constraints**: explicitly defines what MUST NOT be done
- **Grounding**: strict anchoring to provided context
- **Prompt Injection defense**: protection against instruction manipulation
- **Temperature control**: deterministic for code, creative for scripts

Every request passes through Terry before reaching the final model, maximizing quality and precision.

---

## Technical Architecture

Sergio is built on three pillars:

1. **OpenJarvis** (core): the brain that learns, remembers and makes creative decisions
2. **OpenClacky** (hands): controls your system to run Blender, ffmpeg, Nuke, etc.
3. **God's Eye View** (data): connects weather, news, trends APIs for contextual content

**Fly brain (connectome)**: neural circuit inspired by the fruit fly that learns with dopamine, consolidates memory during "sleep" and simulates emotions to predict human resonance.

---

## Feature Status

| Module | Status | Notes |
|---|---|---|
| Video editor (core) | Production | ffmpeg, melt, editing nodes |
| Video Boost IMAX | Production | Complete HDR, upscale, denoise, color pipeline |
| Digital stabilization | Production | Optical flow, gimbal level |
| Studio / VFX | Production | Physics simulations, shaders, Blender |
| Trend radar | Production | Predictive multiplatform analysis |
| Human Thought | Production | Fly brain emotional simulation |
| AI Voiceover | Production | Kokoro local + ElevenLabs premium |
| Neural dubbing | Production | Lip-sync + timbre preservation |
| Multiplatform workflow | Production | Auto-crop, hook rewriting |
| Terry Prompt Eng. | Production | CoT, ToT, delimiters, security |
| Smart search | Production | Visual content indexing |
| Social publishing | Beta | Requires account connection |
| Coach / Health | Hidden | Code preserved, not exposed in UI |
| Calls / WhatsApp | Hidden | Code preserved, not exposed in UI |
| Mental gym | Hidden | Code preserved, not exposed in UI |

---

## Installation

```bash
git clone https://github.com/danicisneros3105-cmd/sergio.git
cd sergio
pip install -e ".[server]"
```

Copy `.env.example` to `.env` and configure your keys (or use pre-configured ones if included).

---

## Quick Start

```bash
# Boost a video to IMAX level
sergio chat "Boost this video to 4K with cinematic color and gimbal stabilization"

# Analyze trends before creating
sergio chat "What trends are about to explode in my fitness niche? Analyze and write a script"

# Conversational editing
sergio chat "Edit this vlog: remove silences, add epic music, and make a 60s trailer"

# Human analysis of content
sergio chat "Analyze this video as if you were human: why would it go viral or not?"
```

Or open the web interface:
```bash
sergio serve
```

---

## Monetization

| Plan | Price | Includes |
|---|---|---|
| **Free** | $0 | Basic editing, 1080p Boost, Kokoro voice, 10 AI calls/day |
| **Pro** | $9.99/mo | 4K Boost, ElevenLabs voice, 100 calls/day, no watermark |
| **Studio** | $29.99/mo | Kling generation, advanced VFX, unlimited, own API |

**Controlled budget**: `budget_control.py` limits spending to $2/day and $15/mo per user. Prioritizes free APIs (Gemini 60 req/min) and local resources (ffmpeg, Kokoro).

---

## License

Apache 2.0 — You can use it, modify it and sell content created with it.

**Credits**: OpenJarvis (Stanford), OpenClacky, God's Eye View, Kokoro, and the open-source community.
