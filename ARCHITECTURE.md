# AI Video Studio
— Architecture

**Status:** Frozen / Approved
**Scope:** This document describes the **implemented v1 system** — Director Studio, Producer Studio, and the FFmpeg Execution Engine, as they actually exist in the repository today. It is the single source of truth. Every future code change must align with it. Where a future change needs to differ, the difference is proposed as an amendment to this document first (§20), not made silently. This revision (v2.0.0, §22) resynchronizes the document with the implementation after Producer Studio (7 milestones) and the FFmpeg Execution Engine (4 milestones) shipped without corresponding doc updates — see §22 for what changed and why. **§24 and §25 are deliberate exceptions to the "implemented only" scope**: §24 (added in v2.1.0) records the *approved design* for a fourth top-level component, the Publishing Engine; §25 (added in v2.2.0) records the *approved design* for a fifth, the Video Generation Engine — both ahead of any implementation, exactly the same design-before-code sequencing the FFmpeg Execution Engine went through, and both clearly labeled as not-yet-built throughout.

---

## 1. Project Vision

AI Video Studio is an **AI Production Planning Platform**, not an AI media generator.

Think of it as a movie production company with three parts:

- **Director Studio** acts like the film director. It researches, writes the story, breaks it into scenes and shots, designs characters and environments, plans camera movement, and writes prompts. Its output is a complete **Production Package**.
- **Producer Studio** acts like the film producer. It takes a Production Package plus media the human has generated with their own preferred tools, validates it, builds a timeline, plans subtitles and music, produces an editing plan, a thumbnail strategy, and publishing metadata. Its output is a complete **Producer Package** — a deterministic, machine-readable *plan* for the final video, not the video itself.
- **The FFmpeg Execution Engine** is the film's actual post-production/render step. It is a separate, fourth top-level component (`execution_engine/`) that consumes a completed Producer Package and compiles + executes it into a real rendered video file, verifying the output before the project is considered done.

Between Director Studio and Producer Studio sits a deliberate, permanent human step: **the human generates the actual images, video, and voice** using whatever tools they prefer — Gemini, Veo, Flux, Midjourney, ElevenLabs, or anything else — and selects the best results. The AI's job in that step is finished the moment the Production Package is exported.

The platform's value is the *planning and assembly intelligence* — story structure, shot coverage, character/environment consistency, prompt quality, editing structure, and finally correct, verified rendering — not the pixels or audio themselves. No component in this system ever generates creative media content; the Execution Engine's own output (a rendered `.mp4`) is a mechanical compilation of already-made planning decisions, not a new creative act.

---

## 2. Design Philosophy

- **Planning, not generation.** No component in this system calls an image, video, or voice generation API as part of its core responsibility. The one exception (a manual, explicitly-invoked preview tool, `agents/image_generator/`) is opt-in via `--generate-images` and never part of the default pipeline.
- **Tool-agnostic by construction.** Prompts and specs in the Production Package are written to work with any external generative tool, not tuned to one vendor.
- **Single responsibility per agent.** Every planner does exactly one job, consumes one typed input contract, and produces one typed output contract. An agent that starts doing two things is a signal to split it.
- **Contracts over conversation.** Agents never pass ad hoc dicts to each other. All inter-agent data exchange happens through typed Pydantic contracts, validated at the boundary.
- **Two-layer validation for LLM-backed agents.** Every LLM output passes through *shape* validation (does the JSON match the schema?) and *business* validation (is the content actually correct?). Deterministic agents (Producer Studio's planning stages, the Execution Engine's pure modules) apply the same "structural validation, then business-rule validation" discipline without an LLM in the loop — see §7's deterministic-agent convention.
- **Projects, not files.** All work is organized around a persistent **Project**, not disconnected UUID-stamped JSON files in a flat folder. **Project Manager** (§4) is its sole gatekeeper: no agent, controller, or the Execution Engine's planning-adjacent modules ever touch a filesystem directly.
- **What a thing is, and how it's written, are different concerns.** Shared Core defines the typed shape of every package and report. Project Manager owns turning those typed objects into files.
- **Incremental evolution.** The architecture evolves by refactoring and extending working code, not by rewriting.
- **The human checkpoint is a feature, not a gap.** The hard boundary between Director Studio's output and Producer Studio's input is intentional.
- **Content verification gates state, not process success alone.** A stage "running without error" is not the same as its output being *correct*. This is explicit in two places: Asset Validation only advances state when `is_valid=True` (not merely when it ran), and the Execution Engine only reaches `VIDEO_RENDERED` when both the ffmpeg process succeeded *and* independent postflight verification of the actual rendered file passed (§7, §9).

---

## 3. High-Level Architecture

```
User / CLI (app.py · producer_app.py · render_app.py)
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│                        Project Manager                         │
│  creation · loading · saving · manifests · metadata ·          │
│  package export · render report/validation export ·            │
│  lifecycle & state management                                  │
└───────┬───────────────────┬───────────────────┬───────────────┘
        │ invokes            │ invokes            │ invokes
        │ typed results only │ typed results only  │ typed results only
        ▼                    ▼                    ▼
┌───────────────┐   ┌───────────────┐   ┌─────────────────────┐
│ Director        │   │ Producer        │   │ FFmpeg Execution      │
│ Studio          │   │ Studio          │   │ Engine                │
│ (planning only, │   │ (planning only, │   │ (compiles + runs      │
│  zero file I/O) │   │  zero file I/O) │   │  ffmpeg; writes the   │
└────────┬────────┘   └────────▲────────┘   │  rendered video and   │
         │                     │             │  its own reports —    │
         ▼                     │             │  the one sanctioned    │
┌───────────────────┐  ┌───────────────────┐ │  media-I/O exception) │
│ Production Package  │─▶│ Human-imported     │ └──────────▲────────────┘
│ (serialized by      │HUMAN│ media (validated│            │ invokes
│  Project Manager)   │generates│ by Project   │            │ typed results only
└───────────────────┘  │ Manager)           │              │
                        └───────────────────┘              │
                                  │                          │
                                  ▼                          │
                        ┌───────────────────┐                │
                        │ Producer Package    │───────────────┘
                        │ (serialized by      │
                        │  Project Manager)    │
                        └───────────────────┘
```

Dependency layering (verified against the actual import graph — see §17):

```
┌───────────────────────────────────────────────────────────┐
│                        Shared Core                           │
│  shared_core/contracts/* (18 typed contract modules)         │
│  shared_core/lookups.py                                      │
└───────────────────────────┬───────────────────────────────┘
                             │
                             ▼
                  ┌───────────────────────┐
                  │     Project Manager      │
                  │ (persistence, lifecycle,  │
                  │  package/report writers)  │
                  └────┬──────┬──────┬────────┘
                  invokes│invokes│invokes
                       ▼       ▼       ▼
          ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐
          │ Director      │ │ Producer      │ │ Execution Engine      │
          │ Studio        │ │ Studio        │ │ (controller +          │
          │ (controller + │ │ (controller + │ │  boundary/pure         │
          │  agents/*)    │ │  agents/*)    │ │  modules)              │
          └──────────────┘ └──────────────┘ └────────────────────┘
```

**Note on direction:** the vision-level chain (Shared Core → Project Manager → studios/engine → Package) describes control and data flow, not raw Python import direction. `project_manager` imports and calls into `director_studio`, `producer_studio`, and `execution_engine` to run stages; none of the three ever imports `project_manager`, imports each other, or touches storage directly — they only accept typed arguments and return typed results (or, for the Execution Engine's boundary modules, perform the one sanctioned category of real I/O: reading/writing media and the ffmpeg/ffprobe subprocess — see §7).

---

## 4. Project Manager Architecture

**Responsibility:** Project Manager is the sole owner of persistence and lifecycle state. It sits between the user-facing entry points (three CLIs today: `app.py`, `producer_app.py`, `render_app.py`) and all three of Director Studio, Producer Studio, and the Execution Engine. None of the three ever touches the filesystem, a database, or object storage directly — they receive typed inputs from Project Manager and return typed outputs to it.

Implemented as a single module, `project_manager/manager.py` (`ProjectManager` class), plus:
- `project_manager/project.py` — the `Project` model and the `ProjectState` enum (§9).
- `project_manager/package_writer.py` — serializes the Production Package.
- `project_manager/producer_package_writer.py` — serializes the Producer Package.
- `project_manager/render_writer.py` — serializes the Execution Engine's two reports (§12).

There is no separate `store.py`/`lifecycle.py` split; `ProjectManager` owns creation, loading, saving, manifests, metadata, package export, render-report export, and state transitions as methods on one class, backed by the writer modules above for serialization.

Project Manager owns:

- **Project creation** — allocate a new project id, initialize `project.json`, set state to `CREATED` (`create_project`).
- **Loading** — reconstruct a `Project`, and whichever typed stage results already exist, from storage (`load_project`, and per-artifact `load_*` methods described in §11/§12).
- **Saving** — persist a stage's typed output against the project (`save_*` methods; several also perform the corresponding state transition — see §9's "Set by" column for exactly which).
- **Manifests** — maintain `manifest.json` inside both the Production Package and the Producer Package.
- **Metadata** — maintain `project.json` and the package-level `metadata.json`.
- **Package exporting** — serialize typed stage outputs into the on-disk package layouts (§10, §11), plus the Execution Engine's `renders/` output (§12).
- **Project lifecycle / state management** — own the state machine (§9) and its transition rules.

Project Manager invokes Director Studio, Producer Studio, or the Execution Engine controller for a given stage, receives typed results back, and is the only component that then writes anything to disk (with the Execution Engine's one named exception — see §7).

Project Manager is deliberately **not** part of Shared Core (§8): it depends on Shared Core, but it owns stateful, application-specific lifecycle logic.

---

## 5. Director Studio Architecture

**Responsibility:** planning only. Director Studio never generates media and never calls a media-generation API as part of its default flow. It performs no filesystem I/O of its own — Project Manager supplies its inputs and persists its outputs.

### Workflow

```
Research (optional, --skip-research to bypass)
   ↓
Story Planning
   ↓
Scene Planning
   ↓
Shot Planning
   ↓
Camera Planning
   ↓
Character Bible
   ↓
Environment Bible
   ↓
Prompt Intelligence (per shot)
   ↓
Voice Script
   ↓
Production Package Export
   ↓
[Image Generation — opt-in manual tool only, --generate-images; never part of the default flow]
```

- Each stage is one agent following the standard agent pattern (§17).
- `director_studio/controller.py` (`DirectorStudioController`) runs every stage in sequence for a project, fails fast on the first `AgentResult(success=False)`, and returns to `app.py`. It performs no filesystem I/O.
- `director_studio/pipeline_helpers.py` holds one small orchestration helper (`select_representative_prompt`, used only by the opt-in image-generation branch) that doesn't belong on any single agent.
- Director Studio's terminal contribution is Project Manager exporting the **Production Package** (§10) and marking the project `PACKAGE_READY`.

---

## 6. Producer Studio Architecture

**Responsibility:** assembly *planning* — timeline, subtitles, music strategy, editing blueprint, thumbnail strategy, and publishing metadata. Producer Studio does **not** render video; that is the Execution Engine's job (§7), a separate component invoked separately, after `EDIT_PLAN_READY`. Producer Studio never plans story content and never edits creative decisions made by Director Studio. Like Director Studio, it performs no filesystem I/O of its own — every stage is fully deterministic (no LLM call).

### Workflow

```
Asset Validation
   ↓
Timeline Planning
   ↓
Subtitle Planning
   ↓
Music Planning
   ↓
Editing Planning
   ↓
Thumbnail Planning
   ↓
Publishing Metadata  ──▶ project state becomes EDIT_PLAN_READY
```

- **Input:** typed data Project Manager assembles — the Production Package's contents (read via `load_prompt_set`/`load_production_plan`/`load_character_sheet`/`load_shot_durations`/`load_scene_moods`/`load_package_metadata`, each reconstructing exactly the fields a given stage needs, either from a legacy flat output file or directly from the on-disk Production Package — both strategies coexist, see §21), plus a manifest of human-imported media Project Manager has confirmed exists in the project's `media/` directory (`scan_media`).
- `producer_studio/controller.py` (`ProducerStudioController`) sequences all seven stages, the same way `DirectorStudioController` does. It never reads or writes a file itself.
- **Asset Validation is the entry gate**: it checks that imported media actually covers what the Production Package expects (per-shot `scene_<id>_shot_<id>.<ext>` naming, plus one `voice_script.<ext>` narration file) before any planning proceeds. A run whose manifest is `is_valid=False` does **not** advance project state — it stops at `PACKAGE_READY` (or stays at `MEDIA_IMPORTED` from a prior partial pass) and reports the specific missing/duplicate/naming issues.
- All seven Producer Studio agents (`asset_validator`, `timeline_planner`, `subtitle_planner`, `music_planner`, `editing_planner`, `thumbnail_planner`, `publishing_planner`) are **deterministic** — they run no LLM and deliberately do not extend `BaseAgent`, since that class is built around the LLM generate/retry/validate cycle. Each still exposes the same `run(input) -> AgentResult` interface as an LLM-backed agent, so the controller sequences them identically. See §17's deterministic-agent convention.
- **Publishing Metadata is the stage that advances state to `EDIT_PLAN_READY`** — it is the sixth and last of the six planning sub-stages (Timeline, Subtitle, Music, Editing, Thumbnail, Publishing Metadata all folded under the `MEDIA_IMPORTED → EDIT_PLAN_READY` window per §9), the same pattern `PROMPTS_COMPLETE` uses for Prompt Intelligence + Voice Script.
- **Output:** typed results (`ValidatedAssetManifest`, `Timeline`, `SubtitlePlan`, `MusicPlan`, `EditingPlan`, `ThumbnailPlan`, `PublishingPlan`) returned to Project Manager, which serializes them into the project's `producer-package/` (§11).

---

## 7. FFmpeg Execution Engine Architecture

**Responsibility:** compile the Producer Package's `EditingPlan` (plus the other five Producer Package artifacts it references) into an ffmpeg invocation, run it, and verify the result — the one component in the system sanctioned to perform real media I/O. It is a **compiler + executor, not a studio**: it invents no content. Every transition, duration, subtitle, and ordering decision was already made by Producer Studio; the Execution Engine only translates an already-frozen plan into ffmpeg arguments and runs them.

Architectural rules (enforced structurally, verified by import inspection):
- Consumes Producer Studio's outputs only — never calls a Director Studio or Producer Studio agent (`execution_engine/` imports only `shared_core.contracts` and `project_manager`).
- Never performs planning — no ordering, duration, or transition decision originates here.
- Never modifies the Producer Package — every Producer Package file is opened read-only.
- Requires project state `EDIT_PLAN_READY` to run at all (also re-admits `VIDEO_RENDERED`, for idempotent re-renders).

### Module layout (`execution_engine/`)

| Module | Role | Layer |
|---|---|---|
| `controller.py` (`ExecutionEngineController`) | Orchestrates the sequence below; the only place that decides whether to execute at all (`--dry-run` skips execution and postflight entirely, here — not in the executor). | orchestration |
| `ffmpeg_detector.py` (`detect_ffmpeg`) | Resolves the `ffmpeg` binary on PATH and confirms `-version` runs cleanly. Reports availability as data (`FFmpegInfo`); never raises itself. | boundary (read-only) |
| `preflight.py` (`verify_media_exists`) | Re-confirms every planned asset/narration file still exists on disk before building a command — Asset Validation approved these paths, but media I/O is real and files can move. | boundary (read-only) |
| `command_builder.py` (`build_command`, `validate_render_request`) | Pure: validates the full provenance chain across all five Producer Package inputs (Timeline/SubtitlePlan/MusicPlan/EditingPlan must all descend from the same Timeline and asset manifest), then builds the ordered `-i` inputs (one per editing segment + one narration audio input) and output config. | pure |
| `filter_graph_builder.py` (`build_visual_filter_graph`) | Pure: compiles the visual timeline's `filter_complex` graph — resolution/fps normalization per input, video-duration trimming, hard cuts via `concat`, scene-boundary crossfades via `xfade`, and edge fade-from/to-black — driven solely by `EditingPlan` (whose segments already carry Timeline-computed timing) and `RenderOptions`. | pure |
| `ffmpeg_executor.py` (`execute`) | The only module that spawns a process or writes the rendered file. Runs the immutable `FFmpegCommandSpec`, writes to a temp file (`<name>.part.<ext>`, preserving the real extension so ffmpeg can infer the container), and atomically renames to the final path only after a verified non-zero-size write. Never raises — always returns a `RenderResult`. | boundary (real media I/O) |
| `ffprobe_client.py` (`probe`) | Read-only: probes the rendered file's actual duration/resolution/fps/stream presence via `ffprobe`, returning `ProbedMedia` (or `None` if unprobeable). | boundary (read-only) |
| `postflight.py` (`validate_render`) | Pure: compares `ProbedMedia` against the render's expected profile (`EditingPlan.total_duration_seconds`, `RenderOptions.resolution`/`.fps`) and produces a `RenderValidationReport`. A `None` probe is an unconditional failure. | pure |
| `errors.py` | `RenderError` hierarchy: `ExecutionEnvironmentError`, `MediaAccessError`, `RenderInputError` — raised only for problems discovered *before* execution can be attempted. Everything that happens once ffmpeg actually runs (non-zero exit, timeout, spawn failure) is reported via `RenderResult`, never raised. | — |
| `ffmpeg_format.py` (`format_seconds`) | Tiny shared helper for embedding durations in argv/filter-graph strings consistently. | pure |

### Execution sequence (`ExecutionEngineController.run`)

1. Load the project; require `status == EDIT_PLAN_READY` (or `VIDEO_RENDERED`, for re-render).
2. Detect ffmpeg (`ExecutionEnvironmentError` if unavailable — the one hard environment gate; ffprobe's absence is *not* gated here, it surfaces later as a postflight check failure).
3. Load all five Producer Package inputs Project Manager reconstructs: `EditingPlan`, `ValidatedAssetManifest`, `Timeline`, `SubtitlePlan`, `MusicPlan`.
4. Validate the request (`validate_render_request`) and confirm every media file still exists (`verify_media_exists`).
5. Build the `FFmpegCommandSpec` (`build_command`, which internally calls `build_visual_filter_graph`).
6. **`--dry-run` stops here** — returns the built command plus `RenderResult(success=True, dry_run=True)`, no execution, no persistence.
7. Execute (`ffmpeg_executor.execute`).
8. If execution succeeded, probe the output (`ffprobe_client.probe`) and validate it (`postflight.validate_render`); if execution failed, there is nothing to probe.
9. Persist via `ProjectManager.save_render_result` (§12) — this is the **only** place `VIDEO_RENDERED` is set, and only when `RenderResult.success` **and** `RenderValidationReport.is_valid` are both `True`.

### What is explicitly NOT yet implemented

- Audio mixing (narration is mapped straight through unfiltered; `MusicPlan`'s fades/ducking are planned data with no corresponding music asset to mix yet — see §21).
- Subtitle burn-in or soft-mux (`RenderOptions.subtitle_mode` is carried but not yet consumed).
- A segmented-concat fallback for very long/complex edits (single `filter_complex` only).
- A publishing executor (`VIDEO_RENDERED → PUBLISHED` has no implementation) — the design is now approved, see §24; implementation has not started.

---

## 8. Shared Core Responsibilities

Shared Core contains everything that is genuinely provider-agnostic, studio-agnostic, stateless, and reusable. Nothing in Shared Core may import from `director_studio/`, `producer_studio/`, `execution_engine/`, or `project_manager/`.

| Component | Location | Responsibility |
|---|---|---|
| Package/report Schemas | `shared_core/contracts/` (18 modules — see §11/§12 for the full list) | Typed Pydantic models defining the shape of every file in the Production Package, the Producer Package, and the Execution Engine's reports — **what a package is.** Every agent's public output contract is (or maps directly onto) one of these types. Project Manager owns serializing instances to disk — Shared Core only defines their shape. |
| Shared lookups | `shared_core/lookups.py` | Cross-referencing helpers (e.g. resolving which environment profile belongs to which scene, which camera shot belongs to which prompt) used by Director Studio's controller. |
| `AgentResult` / `AgentMetadata` | `models.py` (package root) | Generic success/failure envelope returned by every agent run. **Not currently under `shared_core/`** — a known folder-layout deviation, see §21. |
| `BaseAgent` + exception hierarchy | `agents/base/base_agent.py`, `agents/base/exceptions.py` | The universal agent contract for **LLM-backed** agents: `build_prompt → call LLM with retry → validate schema → validate business rules → produce public contract`. Every Director Studio agent, plus none of Producer Studio's (see below), inherits this. **Not currently under `shared_core/`** — a known folder-layout deviation, see §21. |
| LLM Clients (Gemini / GPT / Groq / Gemini Image) | `llm/gemini_client.py`, `llm/gpt_client.py`, `llm/groq_client.py`, `llm/gemini_image_client.py` | Interchangeable text/image-generation clients. Studio code never talks to a provider SDK directly. **Not currently under `shared_core/`** — a known folder-layout deviation, see §21. |
| `utils` (`json_utils`, `logger`) | `utils/json_utils.py`, `utils/logger.py` | JSON extraction from raw LLM text; consistent structured logging. **Not currently under `shared_core/`** — a known folder-layout deviation, see §21. |
| Config | `config.py` (package root, single flat file) | API keys, retry defaults, output directory, and every other setting for every component. The originally-planned per-layer config split (Director/Producer/Project-Manager-specific overlays) was never implemented — see §21. |

**The deterministic-agent convention (Producer Studio + parts of the Execution Engine):** `BaseAgent` assumes an LLM call. Every Producer Studio agent, and conceptually the Execution Engine's pure modules, are deterministic and have no LLM in the loop, so they don't extend it. The established, repeated pattern instead: `agent.py` still exposes `run(input) -> AgentResult` (so controllers sequence them identically to LLM-backed agents), `contract.py` re-exports shared types, `validator.py` (or an equivalently-named pure module) carries the actual logic — but there is no `prompt.py` or `schema.py`, since there is no LLM output to prompt for or shape-validate. This is a **deliberate, now-stable convention**, not a one-off exception — it applies uniformly across all seven Producer Studio agents and the Execution Engine's `command_builder`/`filter_graph_builder`/`postflight`.

Explicitly **not** in Shared Core:
- **Project Manager** (§4).
- Any individual agent.
- The serialization/writing logic for any package or report — that's Project Manager's job.

---

## 9. Project Lifecycle

A **Project** is the single persistent unit of work, owned end-to-end by **Project Manager** (§4).

### Project State Machine

```
CREATED
   ↓
RESEARCHED
   ↓
STORY_COMPLETE
   ↓
SCENES_COMPLETE
   ↓
SHOTS_COMPLETE
   ↓
CAMERA_COMPLETE
   ↓
CHARACTERS_COMPLETE
   ↓
ENVIRONMENTS_COMPLETE
   ↓
PROMPTS_COMPLETE
   ↓
PACKAGE_READY
   ↓
MEDIA_IMPORTED
   ↓
EDIT_PLAN_READY
   ↓
VIDEO_RENDERED
   ↓
PUBLISHED   ← not yet implemented; design approved, see §24
```

All 13 implemented states exist in `project_manager/project.py`'s `ProjectState` enum. `PUBLISHED` is defined nowhere in code yet — no publishing executor exists. Its design (module layout, contracts, retry strategy, gating rule) is approved and recorded in §24, following the exact same "design first, implement in incremental milestones" sequencing the FFmpeg Execution Engine used.

| State | Set by (method) | Meaning |
|---|---|---|
| `CREATED` | `ProjectManager.create_project` | Project scaffold allocated; no stages run yet. |
| `RESEARCHED` | `ProjectManager.save_research_brief` (Director Studio's Research stage) | Research returned a validated `ResearchBrief`. Skipped entirely when `--skip-research` is passed — the project simply proceeds to `STORY_COMPLETE` without passing through this state. |
| `STORY_COMPLETE` | `ProjectManager.save_story_plan` | Story Planner returned a validated `ProductionPlan`. |
| `SCENES_COMPLETE` | `ProjectManager.save_storyboard` | Scene Planner returned a validated `Storyboard`. |
| `SHOTS_COMPLETE` | `ProjectManager.save_shot_plan` | Shot Planner returned a validated `ShotPlan`. |
| `CAMERA_COMPLETE` | `ProjectManager.save_camera_plan` | Camera Planner returned a validated `CameraPlan`. |
| `CHARACTERS_COMPLETE` | `ProjectManager.save_character_sheet` | Character Planner returned a validated `CharacterSheet`. |
| `ENVIRONMENTS_COMPLETE` | `ProjectManager.save_environment_sheet` | Environment Planner returned a validated `EnvironmentSheet`. |
| `PROMPTS_COMPLETE` | `ProjectManager.save_voice_script` | Prompt Intelligence (`save_prompt_set`, no state change on its own) **and** Voice Script have both completed — Voice Script's save is the one that advances state, since it always runs second. |
| `PACKAGE_READY` | `ProjectManager.export_production_package` | Production Package fully serialized and manifest written. |
| `MEDIA_IMPORTED` | `ProjectManager.save_asset_manifest` | Human has placed media into `media/`; Asset Validation ran **and** `manifest.is_valid` is `True`. An invalid manifest is still persisted (for its diagnostic issues) but does **not** advance state. |
| `EDIT_PLAN_READY` | `ProjectManager.save_publishing_metadata` | Timeline, Subtitle, Music, Editing, Thumbnail, and Publishing Metadata planning have **all** completed — Publishing Metadata's save is the one that advances state, since it always runs last. |
| `VIDEO_RENDERED` | `ProjectManager.save_render_result` | The FFmpeg Execution Engine produced a rendered file **and** postflight validation confirmed it matches the expected duration/resolution/fps/streams. A successful ffmpeg exit alone is insufficient — see §7. |
| `PUBLISHED` | *(not implemented — design approved, §24)* | Reserved for the Publishing Engine (§24): `PublishResult.success` **and** `PublishValidationReport.is_valid` both `True`, same "process success is necessary but not sufficient" pattern as `VIDEO_RENDERED`. |

Finer-grained per-agent progress within a state is tracked as a sub-field on the project record (e.g. `source_timeline_id`, `source_subtitle_plan_id`, `rendered_video_path`) rather than as additional top-level states, so the state machine always matches the ladder above exactly. The (designed, not yet implemented) Video Generation Engine follows this same rule deliberately — see §25.10.

### Rules

- A Project is created once, with a stable id, and evolves in place.
- **Project Manager is the only writer of project state and the only component with filesystem access**, except the Execution Engine's one sanctioned exception (§7).
- Projects are self-contained: everything needed to resume work — at any lifecycle stage — lives inside `projects/<project_id>/`.

---

## 10. Production Package Specification

Written by `project_manager/package_writer.py` into `projects/<project_id>/production-package/`:

| File | Produced by | Contents |
|---|---|---|
| `research_brief.json` | Research | Supporting context; `{"status": "skipped", ...}` when bypassed. |
| `story.md` | Story Planner | Human-readable story: title, logline, theme, tone, characters, scenes. |
| `scene_plan.json` | Scene Planner | Scene-level breakdown: setting, mood, characters present, duration. |
| `shot_plan.json` | Shot Planner | Per-scene shot list. |
| `camera_plan.json` | Camera Planner | Per-shot camera angle and movement. |
| `character_bible.json` | Character Planner | One visual profile per character. |
| `environment_bible.json` | Environment Planner | One visual profile per unique setting. |
| `image_prompts.json` | Prompt Intelligence | Final image-generation prompt per shot. |
| `video_prompts.json` | Prompt Intelligence | Final motion/camera prompt per shot. |
| `voice_script.txt` | Voice Script | Full narration script, one paragraph per scene in ascending `scene_id` order (paragraphs are joined with a blank line, and carry no explicit scene markers — Producer Studio's Subtitle Planning relies on that fixed ordering to re-pair text with scenes, see §21). |
| `metadata.json` | Project Manager | Package-level metadata: project id, generation timestamps, target duration, tone, audience, art style. |
| `manifest.json` | Project Manager | Index of every file with description and status. |

---

## 11. Producer Package Specification

Written by `project_manager/producer_package_writer.py` into `projects/<project_id>/producer-package/`, only after Asset Validation has passed:

| File | Produced by | Contents |
|---|---|---|
| `asset_manifest.json` | Asset Validation | Per-shot media coverage report: missing, duplicate, and naming issues; `is_valid`. |
| `timeline_plan.json` | Timeline Planning | Clip ordering, start/end times, per-scene voice segments. |
| `subtitle_plan.json` | Subtitle Planning | Time-aligned subtitle cues. |
| `music_plan.json` | Music Planning | Per-scene mood, tempo, intensity, fades, narration ducking windows. |
| `editing_plan.json` | Editing Planning | Merged, deterministic editing blueprint: per-shot segments referencing resolved assets, subtitle cue indices, music cues, transitions (`cut`/`crossfade`/`fade_from_black`/`fade_to_black`), and effects placeholders. |
| `thumbnail_plan.json` | Thumbnail Planning | Composition, focal subject, emotion, text-safe areas, and a generation prompt per variant. |
| `publishing_metadata.json` | Publishing Metadata | Canonical + YouTube-specific metadata: title, description, keywords, hashtags, category, language, playlist, visibility. |
| `manifest.json` | Project Manager | Index of every file present with description and status. |

Each type above is defined once in `shared_core/contracts/` and re-exported (never redefined) by its producing agent's `contract.py`: `asset_manifest.py`, `timeline.py`, `subtitle.py`, `music_plan.py`, `editing_plan.py`, `thumbnail_plan.py`, `publishing_metadata.py`.

---

## 12. Render Output Specification

Written by `execution_engine/ffmpeg_executor.py` (the video file) and `project_manager/render_writer.py` (the two reports) into `projects/<project_id>/renders/`, only on a non-dry-run render attempt:

| File | Written by | When | Contents |
|---|---|---|---|
| `video.mp4` | `ffmpeg_executor.execute` | Only on a verified successful ffmpeg exit (non-zero-size output, atomically renamed from a temp file). | The rendered video. |
| `render_report.json` | `render_writer.write_render_reports` | Every attempted (non-dry-run) render — success or failure. | `RenderResult`: execution-process diagnostics — exit code, timing, stderr tail on failure. Kept deliberately separate from quality verification. |
| `render_validation.json` | `render_writer.write_render_reports` | Only when a render produced a file to probe (`RenderResult.success == True`). | `RenderValidationReport`: output-quality verdict — per-check pass/fail (video/audio stream presence, resolution, fps, duration) plus the raw `ProbedMedia` facts. **This is the only thing that gates `VIDEO_RENDERED`** (§9). |

Unlike the Production and Producer Packages, `renders/` has no overall `manifest.json` index — a known, minor asymmetry (§21).

Project Manager reconstructs the Execution Engine's typed inputs from the Producer Package via: `load_asset_manifest`, `load_editing_plan`, `load_producer_timeline`, `load_subtitle_plan`, `load_music_plan` (all read the corresponding file above directly, as full typed dumps), plus `get_render_dir` (hands out `renders/`'s location without creating it) and `save_render_result` (writes both reports and performs the `VIDEO_RENDERED` transition).

---

## 13. Folder Structure

This is the actual repository layout, verified against the filesystem — not an aspirational target.

```
ai_video_studio/                        # package root (also the repo's inner directory)
├── app.py                              # Director Studio CLI
├── producer_app.py                     # Producer Studio CLI
├── render_app.py                       # FFmpeg Execution Engine CLI
├── config.py                           # single flat settings module (§8, §21)
├── models.py                           # AgentResult, AgentMetadata (§8, §21)
│
├── shared_core/
│   ├── lookups.py
│   └── contracts/                      # one module per typed contract, re-exported via __init__.py
│       ├── asset_manifest.py           production_plan.py       storyboard.py
│       ├── camera_plan.py              prompt_set.py             subtitle.py
│       ├── character_sheet.py          publishing_metadata.py    thumbnail_plan.py
│       ├── editing_plan.py             render.py                 timeline.py
│       ├── environment_sheet.py        research.py               voice_script.py
│       └── music_plan.py               shot_plan.py
│
├── agents/                             # FLAT — shared by both studios; not nested per-studio (§21)
│   ├── base/                           # base_agent.py, exceptions.py — BaseAgent lives here, not shared_core (§21)
│   ├── research/  story_planner/  scene_planner/  shot_planner/  camera_planner/
│   ├── character_planner/  environment_planner/  prompt_generator/  voice_script/
│   │        ↑ Director Studio agents (LLM-backed, five-file pattern)
│   ├── image_generator/                # opt-in manual tool only, never in the default pipeline
│   ├── asset_validator/  timeline_planner/  subtitle_planner/  music_planner/
│   ├── editing_planner/  thumbnail_planner/  publishing_planner/
│   │        ↑ Producer Studio agents (deterministic, reduced pattern — §8)
│
├── llm/                                # NOT under shared_core (§21)
│   ├── gemini_client.py  gpt_client.py  groq_client.py  gemini_image_client.py
│
├── utils/                              # NOT under shared_core (§21)
│   ├── json_utils.py  logger.py
│
├── director_studio/
│   ├── controller.py                   # DirectorStudioController
│   └── pipeline_helpers.py             # select_representative_prompt
│
├── producer_studio/
│   └── controller.py                   # ProducerStudioController
│
├── execution_engine/                   # NOT documented before this revision (§22)
│   ├── controller.py       ffmpeg_detector.py    preflight.py
│   ├── command_builder.py  filter_graph_builder.py
│   ├── ffmpeg_executor.py  ffprobe_client.py      postflight.py
│   ├── errors.py            ffmpeg_format.py
│
├── project_manager/
│   ├── manager.py                      # ProjectManager — no separate store.py/lifecycle.py (§21)
│   ├── project.py                      # Project, ProjectState
│   ├── package_writer.py               # Production Package
│   ├── producer_package_writer.py      # Producer Package
│   └── render_writer.py                # render_report.json / render_validation.json
│
├── outputs/                            # OUTPUT_DIR root
│   ├── *.json                          # legacy flat per-stage files (still read back — §21)
│   └── projects/<project_id>/
│       ├── project.json
│       ├── production-package/         # §10
│       ├── media/{images,video,audio}/ # human-imported assets
│       ├── producer-package/           # §11
│       └── renders/                    # §12
│
└── tests/
    ├── shared_core/  project_manager/  integration/
    └── test_*.py                       # one file per agent/pure module, flat under tests/
```

`.gitignore` marks `__pycache__/`, but a number of `.pyc` files committed before that rule remain tracked (harmless bytecode-cache churn, not source — §21).

---

## 14. Data Flow

### Director Studio (per project)

```
Project Manager creates project
      │
      ▼
Research (optional) ──► ResearchBrief
      ▼
Story Planner ──► ProductionPlan
      ▼
Scene Planner ──► Storyboard
      ▼
Shot Planner ──► ShotPlan
      ▼
Camera Planner ──► CameraPlan  (consumes ShotPlan)
      ▼
Character Planner ──► CharacterSheet
      ▼
Environment Planner ──► EnvironmentSheet
      ▼
Prompt Intelligence ──► PromptSet  (one ShotPrompt per shot; consumes everything upstream)
      ▼
Voice Script ──► VoiceScript  (consumes ProductionPlan + Storyboard)
      ▼
Project Manager serializes production-package/ + manifest.json
      ▼
Project Manager sets project state = PACKAGE_READY
```

### Human step

The human places generated images/video into `media/images/` and `media/video/` (named `scene_<id>_shot_<id>.<ext>`) and narration audio into `media/audio/voice_script.<ext>`.

### Producer Studio (per project)

```
Project Manager loads project (requires status >= PACKAGE_READY)
      │
      ▼
Asset Validation ──► ValidatedAssetManifest (consumes media/ + PromptSet)
      │
      ▼ (only if is_valid)
Project Manager sets project state = MEDIA_IMPORTED
      │
      ▼
Timeline Planning ──► Timeline (consumes ValidatedAssetManifest + shot durations from shot_plan.json)
      ▼
Subtitle Planning ──► SubtitlePlan (consumes Timeline + voice_script.txt)
      ▼
Music Planning ──► MusicPlan (consumes Timeline + SubtitlePlan + scene moods from scene_plan.json)
      ▼
Editing Planning ──► EditingPlan (consumes ValidatedAssetManifest + Timeline + SubtitlePlan + MusicPlan)
      ▼
Thumbnail Planning ──► ThumbnailPlan (consumes EditingPlan + ProductionPlan + CharacterSheet)
      ▼
Publishing Metadata ──► PublishingPlan (consumes EditingPlan + ThumbnailPlan + ProductionPlan + package metadata.json)
      │
      ▼
Project Manager sets project state = EDIT_PLAN_READY
```

### FFmpeg Execution Engine (per project, separate CLI invocation — `render_app.py`)

```
Project Manager loads project (requires status == EDIT_PLAN_READY, or VIDEO_RENDERED for re-render)
      │
      ▼
Detect ffmpeg (ExecutionEnvironmentError if unavailable)
      ▼
Load EditingPlan + ValidatedAssetManifest + Timeline + SubtitlePlan + MusicPlan from producer-package/
      ▼
Validate provenance chain + confirm media still exists on disk
      ▼
Build FFmpegCommandSpec (filter_complex compiled from EditingPlan + RenderOptions)
      │
      ├── --dry-run: print the command, stop here (nothing executed, nothing written)
      │
      ▼
Execute ffmpeg ──► video.mp4 (atomic write) + RenderResult
      │
      ▼ (only if RenderResult.success)
Probe the output (ffprobe) ──► ProbedMedia
      ▼
Validate against expected profile ──► RenderValidationReport
      │
      ▼
Project Manager writes render_report.json + render_validation.json
      │
      ▼ (only if RenderResult.success AND RenderValidationReport.is_valid)
Project Manager sets project state = VIDEO_RENDERED
```

At every arrow, the object crossing it is a typed Pydantic contract, never a raw dict.

---

## 15. Agent Responsibilities

### Director Studio

| Agent | Input | Output | Single Responsibility |
|---|---|---|---|
| Research | raw idea / topic | `ResearchBrief` | Gather supporting context before story writing. |
| Story Planner | `ResearchBrief` (optional) + raw idea | `ProductionPlan` | Turn an idea into structured story: title, logline, characters, scenes. |
| Scene Planner | `ProductionPlan` | `Storyboard` | Break each scene into a shot list — no camera detail. |
| Shot Planner | `Storyboard` | `ShotPlan` | Confirm/refine per-shot narrative beats. |
| Camera Planner | `ShotPlan` | `CameraPlan` | Assign camera angle/movement per shot. |
| Character Planner | `ProductionPlan` | `CharacterSheet` | One consistent visual profile per character. |
| Environment Planner | `ProductionPlan` | `EnvironmentSheet` | One consistent visual profile per unique setting. |
| Prompt Intelligence | everything upstream | `PromptSet` | Compose final, tool-ready image/video prompts per shot. |
| Voice Script | `ProductionPlan` + `Storyboard` | `VoiceScript` | Write the full narration script. |

### Producer Studio (all deterministic — §8)

| Agent | Input | Output | Single Responsibility |
|---|---|---|---|
| Asset Validation | media/ + `PromptSet` | `ValidatedAssetManifest` | Confirm imported media covers what the package expects. |
| Timeline Planning | `ValidatedAssetManifest` + shot durations | `Timeline` | Sequence validated assets against planned durations. |
| Subtitle Planning | `Timeline` + `voice_script.txt` | `SubtitlePlan` | Segment and time-align narration text to the timeline. |
| Music Planning | `Timeline` + `SubtitlePlan` + scene moods | `MusicPlan` | Plan per-scene mood, tempo, fades, and narration ducking. |
| Editing Planning | `ValidatedAssetManifest` + `Timeline` + `SubtitlePlan` + `MusicPlan` | `EditingPlan` | Merge everything into one deterministic editing blueprint. |
| Thumbnail Planning | `EditingPlan` + `ProductionPlan` + `CharacterSheet` | `ThumbnailPlan` | Compose a thumbnail strategy and generation prompt. |
| Publishing Metadata | `EditingPlan` + `ThumbnailPlan` + `ProductionPlan` + package metadata | `PublishingPlan` | Compose canonical + YouTube publishing metadata. |

No agent calls another agent — sequencing is the controller's job (§16), persistence is Project Manager's job (§4).

---

## 16. Orchestration Flow

- **One controller per studio, plus the Execution Engine's own controller.** `DirectorStudioController`, `ProducerStudioController`, and `ExecutionEngineController` are each the only component that knows the stage order within its own component. Agents don't know what runs before or after them.
- **Project Manager mediates everything.** Controllers receive typed inputs as arguments and return typed results. They never call `open()`, never query storage, never decide file paths.
- **Fail-fast per stage.** A stage returning `AgentResult(success=False)` (or, in the Execution Engine, a pre-execution `RenderError`) stops the run immediately.
- **No cross-studio calls, and no studio (or the Execution Engine) ever imports Project Manager.** Verified by import inspection (§3) — zero violations found as of this revision.

---

## 17. Coding Standards

- **Five-file agent pattern for LLM-backed agents**: `agent.py` (extends `BaseAgent`), `contract.py`, `schema.py`, `prompt.py`, `validator.py`.
- **Reduced three-file pattern for deterministic agents** (§8): `agent.py` (does not extend `BaseAgent`), `contract.py`, `validator.py` (or an equivalently pure module) — no `prompt.py`/`schema.py`, since there is no LLM output. Applies to all seven Producer Studio agents.
- **Two-layer validation** for LLM-backed agents: schema validation for shape, `validator.py` for business rules. Deterministic agents apply business-rule validation only (there is no LLM shape to validate).
- **All inter-module data is a typed Pydantic model.** Any type used across a package boundary is defined once in `shared_core/contracts/`; every agent's own `contract.py` re-exports rather than redefines it. Verified: zero duplicate contract definitions found (§21).
- **No agent imports another agent.** Verified by import inspection — holds with zero exceptions.
- **No media-generation API calls inside any agent**, except the opt-in `agents/image_generator/` (manual tool, never in the default pipeline) and the Execution Engine's `ffmpeg_executor.py`/`ffprobe_client.py` (the one sanctioned real-media-I/O exception, §7).
- **Director Studio, Producer Studio, and the Execution Engine's orchestration/pure modules perform no filesystem I/O.** All persistence goes through Project Manager. The Execution Engine's boundary modules (`ffmpeg_detector`, `preflight`, `ffmpeg_executor`, `ffprobe_client`) are the sole exception, and only for media/subprocess access — never for `project.json`, any manifest, or any package file.
- **LLM provider is always injected**, never hardcoded inside an agent.
- **Errors use the existing exception hierarchies**: `LLMCallError`/`SchemaValidationError`/`ContractViolationError` (`agents/base/exceptions.py`) for agents; `ExecutionEnvironmentError`/`MediaAccessError`/`RenderInputError` (`execution_engine/errors.py`) for pre-execution Execution Engine failures. Execution-phase outcomes (a failed ffmpeg run) are never exceptions — they're a `RenderResult(success=False, ...)`, the same "reportable, not exceptional" convention `ValidatedAssetManifest.is_valid=False` established.
- **Logging** goes through `utils/logger.py`'s `get_logger(name)` — no ad hoc `print()`, except each CLI's final structured JSON report to stdout.
- **Config**: currently one flat `config.py` for everything (§8, §21) — the originally-planned per-layer split was never implemented.

---

## 18. Testing Strategy

268 tests, all passing as of this revision (`python -m pytest -q`).

- **Pure modules get direct, deterministic unit tests** — the majority of the suite. Every `validator.py` (or equivalently pure module: `command_builder.py`, `filter_graph_builder.py`, `postflight.py`) has its own test file exercising business-rule/logic branches with no mocking needed, since these modules make no external calls.
- **Boundary modules are tested with mocks, never real external calls, in the automated suite.** LLM-backed agents are tested via a fake/mocked LLM client. `ffmpeg_detector`/`ffmpeg_executor`/`ffprobe_client` are tested by monkeypatching `subprocess.run` — no real ffmpeg process runs in `pytest`.
- **Controllers are tested via integration tests**, not isolated unit tests — `tests/integration/test_pipeline.py` (Director Studio, mocked LLM), `test_producer_pipeline.py` (Producer Studio, real deterministic logic end-to-end), `test_render_pipeline.py` (Execution Engine, real Director+Producer pipeline feeding a real `EditingPlan`, with the ffmpeg executor and ffprobe prober both injectable/fake by default).
- **Project Manager has its own test file** (`tests/project_manager/test_manager.py`) covering create/load/save/state-transition behavior and package/report serialization round-trips for all three package types.
- **Real-binary verification is a deliberate, manual, non-automated step**, not part of `pytest`: each Execution Engine milestone's completion included a real invocation of `render_app.py` against real ffmpeg/ffprobe (with synthetically generated but genuinely decodable media) as a one-time sanity check, then cleaned up — this keeps the automated suite hermetic and fast while still validating against the real binary before considering a milestone done.
- **CLI verification is likewise manual**: each studio/engine's CLI is exercised by hand against the same recurring demo project at the end of every milestone, not scripted into `pytest`.

---

## 19. Dependency Boundaries

Verified by direct import-graph inspection (not just declared as a rule):

- `shared_core/` depends on nothing else in the repository.
- `project_manager/` depends only on `shared_core/`.
- `agents/*` depend only on `shared_core/` and their own package (`agents/base/`, or their own `agents/<name>/`) — zero agent-to-agent imports found.
- `director_studio/`, `producer_studio/` depend on `shared_core/` and `agents/*` (via their controllers) — neither imports `project_manager`, the other studio, or `execution_engine`.
- `execution_engine/` depends only on `shared_core/contracts` and `project_manager` — zero imports of any `agents/*` module, verified.
- `project_manager/` is the only package that imports `director_studio`, `producer_studio`, and `execution_engine` — and only their controllers.

This makes "no direct filesystem I/O outside Project Manager (and the Execution Engine's one named exception)" a structural guarantee, enforced by which modules are even importable from where — not just a convention.

---

## 20. Migration Roadmap

Phases 1–12 (Director Studio → Producer Studio scaffolding) were completed prior to this revision; see the entries below for what each delivered. Phases 13+ cover Producer Studio's full seven-stage build-out and the FFmpeg Execution Engine, previously undocumented (§22).

| # | Phase | Status | Goal | Key files |
|---|---|---|---|---|
| 1 | Safety net + cleanup | Done | End-to-end pipeline test before refactor. | `tests/integration/test_pipeline.py` |
| 2 | Extract controller | Done | `app.py` becomes a thin CLI wrapper. | `director_studio/controller.py` |
| 3 | Relocate shared lookups | Done | Cross-agent lookups centralized. | `shared_core/lookups.py` |
| 4 | Introduce Project Manager | Done | Project model, persistence, lifecycle state machine. | `project_manager/{project,manager}.py` |
| 5 | Cut over to Project Manager-owned output | Done | Production Package schema in Shared Core; `package_writer.py` is the sole serializer. | `shared_core/contracts/*`, `project_manager/package_writer.py` |
| 6 | Stop auto image generation | Done | Image generation opt-in only (`--generate-images`). | `director_studio/controller.py`, `app.py` |
| 7 | Shot Planner + Camera Planner | Done | Scene Planner narrowed to shot structure; camera detail split out. | `agents/shot_planner/*`, `agents/camera_planner/*` |
| 8 | Research agent | Done | Optional first stage feeding Story Planner. | `agents/research/*` |
| 9 | Voice Script agent | Done | `voice_script.txt` production. | `agents/voice_script/*` |
| 10 | Split config into shared + overlays | **Not done** | Still one flat `config.py` — see §21. | — |
| 11 | Producer Studio Milestone 1 — Asset Validation | Done | Entry gate: validate imported media against the Production Package. | `agents/asset_validator/*`, `producer_app.py` |
| 12 | Producer Studio Milestone 2 — Timeline Planning | Done | Sequence validated assets into a `Timeline`. | `agents/timeline_planner/*` |
| 13 | Producer Studio Milestone 3 — Subtitle Planning | Done | Segment + time-align narration into `SubtitlePlan`. | `agents/subtitle_planner/*` |
| 14 | Producer Studio Milestone 4 — Music Planning | Done | Per-scene mood/tempo/fade/ducking strategy. | `agents/music_planner/*` |
| 15 | Producer Studio Milestone 5 — Editing Planning | Done | Merge Timeline + Subtitle + Music into one blueprint; transitions, effects placeholders. | `agents/editing_planner/*` |
| 16 | Producer Studio Milestone 6 — Thumbnail Planning | Done | Composition/focal-subject/emotion strategy + prompt. | `agents/thumbnail_planner/*` |
| 17 | Producer Studio Milestone 7 — Publishing Metadata | Done | Canonical + YouTube metadata; advances state to `EDIT_PLAN_READY`. | `agents/publishing_planner/*`; `ProjectState.EDIT_PLAN_READY` added |
| 18 | Execution Engine Milestone 8.1 — Foundation | Done | Detect ffmpeg, validate inputs, build (not run) the ffmpeg command object. | `execution_engine/{controller,command_builder,ffmpeg_detector,preflight,errors}.py`, `render_app.py` |
| 19 | Execution Engine Milestone 8.2 — Visual filter graph | Done | `filter_graph_builder.py`: cut/fade/xfade + resolution/fps normalization. | `execution_engine/filter_graph_builder.py` |
| 20 | Execution Engine Milestone 8.3 — Executor | Done | Real subprocess execution, atomic output, structured `RenderResult`, no exceptions on execution failure. | `execution_engine/ffmpeg_executor.py`; `RenderResult`, frozen `FFmpegCommandSpec` |
| 21 | Execution Engine Milestone 8.4 — Postflight | Done | `ffprobe`-based content verification; gates `VIDEO_RENDERED`. | `execution_engine/{ffprobe_client,postflight}.py`, `project_manager/render_writer.py`; `ProjectState.VIDEO_RENDERED` added |
| 22 | Architecture Synchronization (this revision) | Done | Resync this document with the implemented system. | `ARCHITECTURE.md` only |
| 23 | Publishing executor | **Designed (§24)** — implementation not started | `VIDEO_RENDERED → PUBLISHED`, YouTube first, multi-platform-ready. | `publishing_engine/*` (design only), `shared_core/contracts/publish.py` (design only) |
| 24 | Audio mixing / subtitle burn-in | Not started | Wire `MusicPlan`/`SubtitlePlan` into the filter graph once a music asset source exists. | `execution_engine/filter_graph_builder.py` |
| 25 | Publishing Engine Architecture Design (v2.1.0) | Done | Design-only milestone: architecture, folder structure, contracts, state transitions, retry strategy, and platform abstraction for the fourth top-level component, approved ahead of implementation. | `ARCHITECTURE.md` §24 only — no application code |
| 26 | Video Generation Engine Architecture Design (this revision, v2.2.0) | Done | Design-only milestone: architecture, folder structure, contracts, hybrid image/video rendering model, and provider abstraction (Google Veo named as first target, not implemented) for the fifth top-level component, approved ahead of implementation. | `ARCHITECTURE.md` §25 only — no application code |

---

## 21. Active Technical Debt Ledger

Every item below was verified against the current codebase as of this revision (2026-07-25), not carried forward from memory. An item is removed only once its fix has actually landed.

| # | Item | Accepted at | Severity | Notes |
|---|---|---|---|---|
| 1 | Folder layout drift from this document's own §13: `agents/` is flat (shared by both studios, not nested per-studio), `BaseAgent` lives in `agents/base/` not `shared_core/`, `llm/`/`utils/`/`models.py`/`config.py` sit at the package root rather than under `shared_core/`. | Accumulated Phases 5–21 | Low (functionally harmless; now correctly documented in §13/§8 instead of contradicted) | This document previously described the *target* layout as if it were current. §13 now describes the *actual* layout. Closing this gap for real (moving files) is a future, optional refactor — not required for correctness. |
| 2 | Config split (Phase 10, §20) never implemented — one flat `config.py`. | Roadmap Phase 10, deferred | Low | Still deferred; no functional problem at current scale. |
| 3 | `app.py` never prints the created project's `project_id`. | Discovered during v1.0 audit (2026-07-25) | **High (usability)** | `producer_app.py` and `render_app.py` both *require* `--project-id`; there is currently no way to obtain it from `app.py`'s own output. The Director → Producer → Execution Engine CLI handoff is broken for real human use even though the underlying pipeline is complete and correct. Not fixed in this (documentation-only) revision. |
| 4 | `project_id` is used unsanitized in `ProjectManager._project_dir` (`OUTPUT_DIR / "projects" / project_id`), with no validation that it's a well-formed id. | Discovered during v1.0 audit (2026-07-25) | **High (security, latent)** | Path-traversal shape. Low current exposure (local, single-user CLI), but cheap to close at this one choke point before any hosted/multi-tenant exposure. Not fixed in this (documentation-only) revision. |
| 5 | `D:\ai_video_studio\.agents\` — a git-tracked, 23-file duplicate of old agent code, entirely unreferenced by the active package. | Discovered during v1.0 audit (2026-07-25) | Medium (dead code, repo hygiene) | Should be deleted. Not fixed in this (documentation-only) revision. |
| 6 | `renders/` has no `manifest.json` index, unlike the Production and Producer Packages. | Introduced at Execution Engine Milestone 8.4 | Low | Three self-describing files (`video.mp4`, `render_report.json`, `render_validation.json`); low value in an index today. |
| 7 | `datetime.utcnow()` (deprecated in Python) used in 19 files — every `shared_core/contracts/*` default factory plus `agents/base/base_agent.py`. | Accumulated since Phase 5 | Low | Deprecation warning only, consistent everywhere; not a correctness bug. |
| 8 | Two different Producer Studio input-reload strategies coexist: some stages reconstruct a full typed object from a legacy flat `outputs/*.json` file (`load_prompt_set`, `load_production_plan`, `load_character_sheet`), others read one field directly from the on-disk Production Package (`load_shot_durations`, `load_scene_moods`, `load_package_metadata`). | Accumulated across Producer Studio Milestones 1–7 | Low | Both work correctly; noted as worth reconciling, not blocking. |
| 9 | Audio mixing and subtitle burn-in are unimplemented — `MusicPlan`/`SubtitlePlan` are fully planned but not yet wired into the filter graph. | Execution Engine v1 scope boundary | Low (scoped, not a defect) | Deliberate v1 scope limit (§7) — no music asset source exists yet for mixing to act on. |
| 10 | `RenderOptions.timeout_seconds` defaults to unbounded (`None`) unless explicitly passed. | Execution Engine Milestone 8.3 | Low | The originally-designed "derive a timeout from duration × multiplier" default was never implemented. |
| 11 | `.pyc` files committed before `__pycache__/` was gitignored remain tracked, and continue to show as modified on every local test run. | Pre-existing, predates Producer Studio | Low | Harmless bytecode churn; a future cleanup could `git rm --cached` them. |
| 12 | `README.md` is a two-line placeholder — no setup instructions, no `.env`/ffmpeg prerequisites, no pointer to this document. | Pre-existing | Low | Low severity for the project's current (effectively solo) usage. |

**Items resolved by this revision (Phase 22):** the prior version of this document itself was the largest technical-debt item — stale folder structure, an entirely undocumented `execution_engine/`, a Migration Roadmap and Technical Debt Ledger that stopped at Phase 7, and a state-machine table that misattributed `EDIT_PLAN_READY`/`VIDEO_RENDERED` to "Producer Studio" generically instead of the specific gating methods. All resolved here.

---

## 22. Version History

| Version | Date | Summary |
|---|---|---|
| 1.0.0 | 2026-07-21 | Initial frozen architecture, written against Director Studio + a partially-scaffolded Producer Studio design. Migration Roadmap covered Phases 1–12; Technical Debt Ledger closed out through Phase 7. |
| — (`director-studio-v1.0`) | 2026-07-24 | Director Studio tagged complete: Phases 1–9 (Research, Story/Scene/Shot/Camera Planning, Character/Environment Bibles, Prompt Intelligence, Voice Script, opt-in image generation). |
| — (`producer-studio-v1.0`) | 2026-07-25 | Producer Studio tagged complete: all seven planning stages (Asset Validation through Publishing Metadata), `EDIT_PLAN_READY` added to the state machine. Not reflected in this document at the time. |
| — (`execution-engine-v1.0`) | 2026-07-25 | FFmpeg Execution Engine tagged complete: detection/validation/command-building (8.1), visual filter graph (8.2), real execution with atomic output (8.3), postflight verification gating `VIDEO_RENDERED` (8.4). Not reflected in this document at the time. |
| 2.0.0 | 2026-07-25 | **Architecture Synchronization (Milestone 9, documentation-only).** Rewrote this document to match the implemented system: added §7 (FFmpeg Execution Engine, previously undocumented), added §11/§12 (Producer Package and Render Output specifications), corrected §13 (folder structure) to the actual flat/root-level layout, corrected §9's state-machine "Set by" column to name the actual gating methods, corrected §8 (Shared Core) to reflect `BaseAgent`/`llm`/`utils`/`models.py`/`config.py`'s actual locations, expanded the Migration Roadmap (§20) through Phase 24, replaced the Technical Debt Ledger (§21) with a freshly-verified list (including two newly-discovered high-severity items: `app.py` not printing `project_id`, and unsanitized `project_id` in path construction — neither fixed here, both explicitly deferred), and added this Version History section. No application code was changed. |
| 2.1.0 | 2026-07-26 | **Publishing Engine Architecture Design (design-only milestone).** Added §24: the approved architecture for the fourth top-level component — folder structure, the new `shared_core/contracts/publish.py` contract module, platform abstraction (`PublishingPlatform` interface + registry, YouTube first), retry strategy (transient/permanent classification, resumable uploads, idempotent re-publish), the `VIDEO_RENDERED → PUBLISHED` state transition and its gating rule, and the `publishing/` output specification — all mirroring the Execution Engine's (§7) pure/boundary split and process-vs-verification report separation. Cross-referenced from §7, §9, §20, and §23. Nothing in §24 is implemented; no application code was changed. |
| **2.2.0 (this revision)** | **2026-08-02** | **Video Generation Engine Architecture Design (design-only milestone).** Added §25: the approved architecture for the fifth top-level component — folder structure, the new `shared_core/contracts/video_generation.py` contract module, provider abstraction (`VideoGenerationProvider` interface + registry, Google Veo named as the first target, not implemented), the per-shot `ShotMediaSelection` hybrid-mode model, and the `video_manifest.json` output specification. Documents a key existing finding: the hybrid image/video rendering model this design needed (`TimelineClip.asset_type`, `ValidatedAsset.video_path`, `filter_graph_builder`'s video-trim branch) was already implemented ahead of need during the Execution Engine milestones, so Producer Studio and the Execution Engine require zero code changes. Cross-referenced from §1, §9, §20, and §23. Nothing in §25 is implemented; no application code was changed, and no provider API was called. |

---

## 23. Future Expansion Plan

Ideas explicitly out of scope for v1, but consistent with this architecture:

- **Publishing executor** — `VIDEO_RENDERED → PUBLISHED`, consuming `publishing_metadata.json` + the rendered video, following the same controller/boundary-module split as the Execution Engine. Full design (module layout, contracts, retry strategy, platform abstraction) is approved and recorded in §24; only the implementation milestones remain.
- **Video Generation Engine** — an opt-in, automated populator of `media/video/` via external AI video providers (Google Veo first), consuming `video_prompts.json` (already produced today) and slotting into the hybrid image/video rendering model Producer Studio and the Execution Engine already implement. Full design (module layout, contracts, provider abstraction, hybrid-mode selection) is approved and recorded in §25; only the implementation milestones remain.
- **Thumbnail generation executor** — consumes `thumbnail_plan.json`'s prompt to actually produce the thumbnail image; a separate component from video rendering, same reasoning as keeping the Execution Engine single-purpose (§7).
- **Audio mixing** — once a music-generation/selection stage produces a real asset, `MusicPlan`'s already-compiled fades/ducking activate at the filter-graph seam already reserved for them (§7, §21 item 9).
- **Web UI (v1.1)** — a thin FastAPI layer plus a separate Next.js frontend, augmenting (not replacing) the four existing CLIs. Talks to Project Manager and the four controllers exactly as the CLIs do today; adds no second source of truth and no duplicated orchestration logic. Full architecture and phased implementation plan (D1–D7) recorded in the companion document `WEB_DASHBOARD_ARCHITECTURE.md` — design only, not yet implemented.
- **Style preset library**, **per-tool prompt formatting**, **project versioning/diffing**, **multi-format export** (EDL/Premiere XML alongside direct ffmpeg), **batch project generation**, **collaborative projects**, **plugin system for new agents** — all as previously scoped, unchanged by this revision.

---

## 24. Publishing Engine Architecture (Approved Design — Not Yet Implemented)

> **Everything in this section is a design, not a description of running code.** No file listed here exists yet. It is recorded now — following the same sequencing the FFmpeg Execution Engine used (§7's design was approved before Milestone 8.1 was coded) — so implementation can proceed in incremental milestones against an already-agreed shape, instead of the shape being invented ad hoc mid-implementation.

### 24.1 Responsibility & Rules

**Responsibility:** take a project's already-finished `PublishingPlan` (canonical + platform-specific metadata) and already-rendered `video.mp4`, and get them onto an external platform — the *upload/distribution* step, exactly as the Execution Engine is the *render* step. It is the **fourth top-level component**, sitting after the Execution Engine in the pipeline, with its own controller and its own boundary/pure module split.

Architectural rules (same enforcement style as §7 — structural, verified by import inspection once built):

1. **Consumes Producer Package + Execution Engine output only.** `publishing_engine/` imports only `shared_core.contracts` and `project_manager`. It never imports `director_studio`, `producer_studio`, or `execution_engine`, and never calls any agent from any studio.
2. **Never plans.** No title, description, tag, category, or visibility decision originates here — all of that was already decided by Producer Studio's Publishing Metadata stage (§6) and lives in `PublishingPlan`. The Publishing Engine's only "decisions" are mechanical: which platform adapter to invoke and how to retry a failed network call.
3. **Never renders.** It never touches ffmpeg, never opens `filter_graph_builder`, and treats `renders/video.mp4` as an opaque, already-finished file — read-only input, byte-for-byte, the same way the Execution Engine treats Producer Package files as read-only input.
4. **Requires project state `VIDEO_RENDERED` to run at all** (also re-admits `PUBLISHED`, for idempotent re-publish / metadata-only updates — the same re-admission pattern the Execution Engine uses for `VIDEO_RENDERED` re-renders, §7).

### 24.2 Platform Abstraction

A single abstract interface, `PublishingPlatform`, is implemented once per external platform. The controller and every contract are written against this interface only — they never know they're talking to YouTube specifically.

```
publishing_engine/platforms/base.py       # PublishingPlatform — the abstract interface
publishing_engine/platforms/youtube.py    # YouTubePlatform — first, and only v1, implementation
publishing_engine/platforms/registry.py   # name -> implementation lookup (pure)
```

`PublishingPlatform` defines three operations, each boundary (real network I/O), each returning a typed result rather than raising for anything past the pre-flight stage:

| Method | Purpose |
|---|---|
| `authenticate() -> PlatformInfo` | Resolve credentials (from `config.py`/environment, never from a contract) and confirm they're valid. Mirrors `ffmpeg_detector.detect_ffmpeg` — reports availability as data, never raises itself. |
| `upload(video_path, thumbnail_path, publishing_plan, options) -> PublishResult` | Owns the actual upload, including retry/backoff and resumable-session handling (§24.5) internally. The only method that performs a real, potentially slow, potentially retried network operation. |
| `check_status(external_video_id) -> PublishValidationReport` | Poll the platform for post-upload processing state (e.g. YouTube's `processingStatus`) and translate it into the same pass/fail-checks shape `postflight.validate_render` already establishes for renders. |

`publishing_engine/platforms/registry.py` is a pure `{"youtube": YouTubePlatform}` lookup (`resolve_platform(name) -> Type[PublishingPlatform]`, raising `PublishInputError` for an unknown name). **Adding a second platform (TikTok, Instagram, a private CDN) means writing one new class that implements `PublishingPlatform` and adding one registry entry — zero changes to the controller, the contracts, or any other platform's code.** This is the concrete mechanism behind "target YouTube first, support multiple platforms in the design."

`PublishRequest.options.platform` (a plain string, `"youtube"` by default) is the only thing that selects which adapter runs — the same shape as `image_client_factory` already used for the opt-in image-generation tool (§5), not a new pattern.

### 24.3 Contracts (`shared_core/contracts/publish.py` — new, 19th contract module)

Mirrors `render.py`'s established shape exactly: an `Options` input, a `Request` bundle, a process-outcome `Result`, and a separate verification `Report`. **Credentials are never a field on any of these** — resolved live, inside `platforms/youtube.py` only, from `config.py`/environment, and never logged, serialized, or written to any package file or report.

| Contract | Mirrors | Shape |
|---|---|---|
| `PublishOptions` | `RenderOptions` | `platform: str = "youtube"`, `visibility_override: Optional[str] = None` (None = defer to `PublishingPlan.youtube.visibility`), `scheduled_publish_at: Optional[datetime] = None`, `dry_run: bool = False`, `timeout_seconds: Optional[int] = None`, `poll_interval_seconds: int = 10`, `max_poll_attempts: int = 30`. |
| `PlatformInfo` | `FFmpegInfo` | `platform: str`, `available: bool`, `account_label: Optional[str] = None` (e.g. channel name — never a token), `detail: Optional[str] = None`. Never raises on its own; the controller decides whether unavailability is fatal. |
| `PublishRequest` | `RenderRequest` | `publishing_plan: PublishingPlan`, `video_path: str`, `thumbnail_path: Optional[str] = None` (None until a thumbnail-generation executor exists — §24.9), `output_dir: str`, `options: PublishOptions`. |
| `PublishResult` | `RenderResult` | `success: bool`, `dry_run: bool = False`, `platform: str = ""`, `external_video_id: Optional[str] = None`, `external_url: Optional[str] = None`, `started_at`/`finished_at: Optional[datetime]`, `retry_count: int = 0`, `error: Optional[str] = None`, `error_type: Optional[str] = None` (`"upload_failed" | "auth_failed" | "timeout" | "quota_exceeded"`). `success=True` means only that the platform *accepted* the upload — process diagnostics, not verified publication. |
| `PublishValidationCheck` | `RenderValidationCheck` | `name: str` (`"upload_accepted" | "processing_status" | "video_public_state" | "metadata_applied"`), `passed: bool`, `expected: str`, `actual: str`. |
| `PublishValidationReport` | `RenderValidationReport` | `is_valid: bool`, `checks: List[PublishValidationCheck]`, `external_video_id: Optional[str] = None`, `external_url: Optional[str] = None`, `generated_at: datetime`. **This is the only thing that gates `PUBLISHED`** — exactly as `RenderValidationReport.is_valid` alone gates `VIDEO_RENDERED` (§7, §9). |

`PublishingPlan` itself (`shared_core/contracts/publishing_metadata.py`) is **not modified** — it already exists, already carries `canonical`/`youtube` metadata blocks, and is consumed read-only, same as every other Producer Package artifact the Execution Engine reads.

### 24.4 Module Layout (`publishing_engine/`)

| Module | Role | Layer |
|---|---|---|
| `controller.py` (`PublishingEngineController`) | Orchestrates the sequence in §24.6; the only place that decides whether to publish at all (`--dry-run` skips upload and postflight entirely, here — never inside a platform adapter). | orchestration |
| `preflight.py` (`verify_publish_inputs`) | Re-confirms `video_path` still exists and is non-empty, and that `thumbnail_path` (if given) still exists, immediately before upload — same "planning approved it, but I/O is real" justification as the Execution Engine's `preflight.py`. | boundary (read-only) |
| `publish_request_builder.py` (`build_publish_request`, `validate_publish_request`) | Pure: confirms provenance — `PublishingPlan.source_editing_plan_id` must match the `EditingPlan` id recorded against the project's *current* `rendered_video_path`, so a stale metadata plan can never be published against a newer re-render (or vice versa) — then assembles the typed `PublishRequest`. | pure |
| `platforms/base.py` | `PublishingPlatform` abstract interface (§24.2). | interface |
| `platforms/youtube.py` (`YouTubePlatform`) | The only module that makes a real YouTube Data API v3 call. Owns resumable upload session management and all retry/backoff (§24.5). Never raises for a failed upload — always returns `PublishResult`. | boundary (real network I/O) |
| `platforms/registry.py` (`resolve_platform`) | Pure name → implementation lookup (§24.2). | pure |
| `postflight.py` (`validate_publish`) | Pure: interprets a platform's `check_status` result against what a successful publish should look like, producing `PublishValidationReport`. An unreachable/unresolvable status is an unconditional failure, mirroring `postflight.validate_render`'s handling of a `None` probe. | pure |
| `errors.py` | `PublishError` hierarchy — see §24.7. | — |

### 24.5 Retry Strategy

Retry lives **entirely inside the boundary module** (`platforms/youtube.py`) — never in the controller, never in a pure module — the same "boundary owns retry, pure modules can't fail transiently so they don't retry" principle already implicit in `ffmpeg_executor.py` (which itself doesn't retry, because a local subprocess failure isn't transient the way a network call is).

- **Transient vs. permanent classification.** HTTP 5xx, connection timeouts, and 429 (rate limit / quota-per-minute) are transient → retried with exponential backoff + jitter, capped at a bounded number of attempts (default 5, configurable). 401/403 (bad or expired credentials), a permanently exceeded daily quota, and malformed-request errors (400) are permanent → fail immediately into `PublishResult(success=False, error_type="auth_failed" | "quota_exceeded" | "upload_failed")` with zero retries. This mirrors the agent layer's own `LLMCallError`-vs-`SchemaValidationError` (retryable) vs. `ContractViolationError` (not retryable) split in `agents/base/base_agent.py`, adapted to network-call failure modes instead of LLM failure modes — not a new retry philosophy, the same one applied to a different boundary.
- **Resumable uploads make retry safe, not just fast.** YouTube's resumable upload protocol is used deliberately: a retried attempt resumes the same upload session from the last acknowledged byte offset rather than restarting the whole file, so a network blip partway through a multi-hundred-MB upload doesn't waste bandwidth or risk a corrupt duplicate.
- **Idempotency guards against duplicate publishes**, independent of in-upload retry: if `project.status == PUBLISHED` and `project.external_video_id` is already set, re-running the Publishing Engine defaults to a **metadata-update call** (title/description/tags/visibility) against the existing `external_video_id`, not a new upload — the same video is never uploaded twice by a routine re-run. A distinct, explicit "publish as a new video" path (not a default) is the only way to bypass this, deliberately making accidental duplicate uploads hard and duplicate uploads-by-mistake something the controller actively prevents rather than something retry logic has to avoid as a side effect.
- **`PublishResult.retry_count`** records how many attempts the upload actually took, so `publish_report.json` (§24.8) is diagnostic even on eventual success, not just on failure.

### 24.6 Execution Sequence (`PublishingEngineController.run`)

1. Load the project; require `status == VIDEO_RENDERED` (or `PUBLISHED`, for idempotent re-publish/metadata-update).
2. Load `PublishingPlan` (`publishing_metadata.json`) and confirm `rendered_video_path` is set.
3. Validate the request (`publish_request_builder.validate_publish_request`) — provenance check (§24.4) — and confirm the video file still exists (`preflight.verify_publish_inputs`).
4. Resolve the platform adapter (`platforms/registry.resolve_platform`) and authenticate (`platform.authenticate()` — `ExecutionEnvironmentError`-equivalent, `PublishEnvironmentError`, if credentials are missing/invalid; this is the one hard environment gate, same role `ffmpeg_detector` plays in §7).
5. **`--dry-run` stops here** — returns the built `PublishRequest` plus `PublishResult(success=True, dry_run=True)`, nothing uploaded, nothing persisted. This branch lives in the controller, never inside `YouTubePlatform`, for the same reason it lives in `ExecutionEngineController` and not `ffmpeg_executor.execute()` (§7).
6. Upload (`platform.upload(...)`) — retry/backoff and resumable-session handling happen inside this call (§24.5).
7. If upload succeeded, poll for processing completion (`platform.check_status`) and interpret it (`postflight.validate_publish`); if upload failed, there is nothing to poll.
8. Persist via `ProjectManager.save_publish_result` (§24.8) — the **only** place `PUBLISHED` is set, and only when `PublishResult.success` **and** `PublishValidationReport.is_valid` are both `True`.

### 24.7 Errors

`publishing_engine/errors.py` mirrors `execution_engine/errors.py`'s hierarchy and reasoning exactly — raised only for problems discovered before an upload can even be attempted; everything that happens once the network call is actually made is a `PublishResult`, never an exception:

- `PublishError` — base.
- `PublishEnvironmentError` — credentials missing/invalid, or the configured platform has no registered adapter.
- `MediaAccessError` — the rendered video (or thumbnail, if given) is missing/unreadable on disk. *(Reused from `execution_engine/errors.py` rather than redefined — same failure concept, same meaning, no reason for two classes.)*
- `PublishInputError` — `PublishingPlan` missing, invalid, or its provenance doesn't match the current `rendered_video_path` (§24.4).

### 24.8 State Transitions & Output Specification

**State transition:** `VIDEO_RENDERED → PUBLISHED`, set by a new `ProjectManager.save_publish_result` method, gated exactly like `save_render_result` (§7, §9): both `PublishResult.success` and `PublishValidationReport.is_valid` must be `True`, or the project's state is left completely unchanged (no partial/no-op write). No new intermediate "PUBLISHING" state is introduced — the Execution Engine sets no intermediate "RENDERING" state either, only the terminal one, once persistence actually happens.

New `Project` fields (mirroring `rendered_video_path`): `external_platform: Optional[str]`, `external_video_id: Optional[str]`, `external_url: Optional[str]`, `published_at: Optional[datetime]`.

**Output specification** — written by `project_manager/publish_writer.py` into a new `projects/<project_id>/publishing/` directory, mirroring `renders/`'s two-report separation (§12) exactly:

| File | Written by | When | Contents |
|---|---|---|---|
| `publish_report.json` | `publish_writer.write_publish_reports` | Every attempted (non-dry-run) publish — success or failure. | `PublishResult`: process diagnostics — retry count, timing, error on failure. Kept separate from platform-verified outcome, same reasoning as `render_report.json`/`render_validation.json`. |
| `publish_validation.json` | `publish_writer.write_publish_reports` | Only when an upload was accepted (`PublishResult.success == True`). | `PublishValidationReport`: the platform-verified outcome — per-check pass/fail plus the external video id/URL. **This is the only thing that gates `PUBLISHED`.** |

`ProjectManager` additions: `load_publishing_plan` (reads `publishing_metadata.json`, same pattern as `load_editing_plan` etc.), `get_publish_dir` (hands out `publishing/`'s location without creating it), `save_publish_result`.

### 24.9 Explicitly Deferred / Not Designed Yet

- **Scheduled publishing execution** — `PublishOptions.scheduled_publish_at` is carried as a field so a future scheduler can act on it, but no cron/queue/scheduling mechanism is designed here; v1 publishing is synchronous, invoked on demand (mirrors `RenderOptions.subtitle_mode` being carried-but-unconsumed in the Execution Engine's own v1, §7).
- **Simultaneous multi-platform publish** — v1 is one `PublishRequest` → one platform per invocation. A project publishing to both YouTube and a second platform would run the controller twice, producing two independent `PublishResult`/`PublishValidationReport` pairs; a "fan-out to N platforms in one call" orchestration layer is not designed here.
- **Thumbnail upload** depends on a not-yet-built thumbnail-generation executor (§23) actually producing a thumbnail *image* from `ThumbnailPlan`'s prompt — today `ThumbnailPlan` only contains a prompt, not a file. `PublishRequest.thumbnail_path` is `Optional` and will be `None` until that executor exists; `YouTubePlatform.upload` must handle `None` thumbnail (uses the platform's auto-generated thumbnail) as the default v1 case.
- **Credential storage mechanism** (OAuth token file vs. `config.py` env vars vs. a secrets manager) is intentionally left as an implementation-milestone decision, not fixed here — the only hard constraint from this design is that credentials never appear in a `shared_core/contracts` type, a Producer Package file, or a report.

---

## 25. Video Generation Engine Architecture (Approved Design — Not Yet Implemented)

> **Everything in this section is a design, not a description of running code.** No file listed here exists yet. It is recorded now — following the exact same sequencing the FFmpeg Execution Engine (§7) and the Publishing Engine (§24) both used — so implementation can proceed in incremental milestones against an already-agreed shape. No Google Veo (or any other provider) integration is implemented by this section; no API call of any kind is made by writing it.

### 25.1 Responsibility & Rules

**Responsibility:** take a shot's already-finished `video_motion_prompt` (Director Studio's Prompt Intelligence stage, §5, already produces this today — see §25.2) and turn it into a real `.mp4` clip via an external AI video provider, placing it exactly where a human today places a hand-generated video clip: `media/video/scene_<id>_shot_<id>.mp4`. It is the **fifth top-level component**, a peer to Director Studio, Producer Studio, the Execution Engine (§7), and the Publishing Engine (§24) — with its own controller and its own boundary/pure module split, following the same architectural discipline as both.

Architectural rules (same enforcement style as §7/§24 — structural, verified by import inspection once built):

1. **Consumes the Production Package's `PromptSet` only.** `video_generation_engine/` imports only `shared_core.contracts` and `project_manager`. It never imports `director_studio`, `producer_studio`, `execution_engine`, or `publishing_engine`, and never calls any agent from any studio — the exact rule §19 already enforces for `execution_engine/`.
2. **Never plans.** No shot structure, duration, camera treatment, or narrative decision originates here — all of that was already decided by Shot Planner, Camera Planner, and Prompt Intelligence (§5) and lives in `PromptSet`. The Video Generation Engine's only decisions are mechanical: which provider adapter to call, how to poll/retry, and whether a shot was actually requested as VIDEO mode (§25.3).
3. **Never renders the final video.** It never touches `ffmpeg`, never opens `filter_graph_builder.py` or `command_builder.py`. It produces per-shot source clips, which downstream treats exactly like human-imported video — the Execution Engine's job (§7) is unchanged.
4. **Runs at project state `PACKAGE_READY`** (also re-admits `MEDIA_IMPORTED` and `EDIT_PLAN_READY`, for idempotent re-generation of individual shots — e.g. re-rolling one rejected clip without disturbing an otherwise-valid `media/` folder). It does **not** introduce a new top-level `ProjectState`: per §9's own rule ("finer-grained per-agent progress... tracked as a sub-field... rather than as additional top-level states"), generation progress lives on new `Project` sub-fields (§25.10), the same pattern `rendered_video_path` already established.

### 25.2 The Existing Hybrid Hook (why this integrates almost for free)

This is the single most important finding of this design pass, and it changes the entire risk profile of the milestone: **the hybrid image/video data model this milestone asks for already exists and is already load-bearing**, discovered by reading (not assuming) the current pipeline:

- `shared_core/contracts/prompt_set.py`: `ShotPrompt` already carries **both** `image_prompt` and `video_motion_prompt` per shot. Prompt Intelligence already writes `production-package/video_prompts.json` today (`package_writer.py`, `MANIFEST_DESCRIPTIONS`) — nothing downstream currently reads it back; it is exported and then ignored. The milestone's requested "Story → Video Prompts" arrow is **already implemented**.
- `shared_core/contracts/asset_manifest.py`: `ValidatedAsset` already carries **both** `image_path: Optional[str]` and `video_path: Optional[str]` per shot, populated independently by whichever files Asset Validation finds in `media/images/` and `media/video/`.
- `shared_core/contracts/timeline.py`: `TimelineClip.asset_type` is already typed as `"image" | "video" | "black"`, and `agents/timeline_planner/validator.py`'s `_resolve_clip_asset` already contains this exact, already-shipped rule: **"video is preferred over a static image when both exist"** (`Timeline`'s own docstring says so verbatim).
- `shared_core/contracts/editing_plan.py`: `EditingSegment.asset_type` carries the same three-way value straight through from the Timeline.
- `execution_engine/filter_graph_builder.py:170`: already branches on `segment.asset_type == "video"` to apply a `trim=` filter (a video source is conformed to the plan's duration) versus treating an image as already-exact-duration — both paths converge into the same `normalize_expr` and the same `concat`/`xfade` graph.

In other words: **the entire hybrid rendering pipeline this milestone asks for (§25 requirement 4) is not new design — it is already-shipped, already-tested behavior**, apparently built ahead of need during the Execution Engine milestones so that a human could hand-place a mix of images and videos into one project. Nothing in Producer Studio or the Execution Engine needs to change for this milestone. The Video Generation Engine's entire job is to become a new, automated *producer* of the files that already slot into this path — the same role a human's own video-generation workflow (Veo, Runway, etc., used manually, per §1) already plays today, just automated and orchestrated.

### 25.3 Media Mode Selection & Hybrid Rendering

Per-shot mode selection is new (nothing upstream records it today), and is deliberately kept as a small, additive, optional contract rather than a change to `PromptSet`, `ShotPrompt`, or any other existing Director Studio output — preserving requirement 9 (zero migration for old projects) trivially, since old projects simply never have this file:

- `ShotMediaSelection` (new — §25.4): `scene_id`, `shot_id`, `mode: "image" | "video"`. Absence of a selection for a given shot defaults to `"image"` — today's only behavior — so a project that never touches the Video Generation Engine behaves identically to today, byte for byte.
- **Image Mode** (today's default): no selections are made; the human or the opt-in `image_generator` (§5) populates `media/images/`, exactly as now.
- **Video Mode**: every shot is selected `"video"`; the Video Generation Engine populates `media/video/` for the whole project.
- **Hybrid Mode**: a per-shot mix — e.g. a hero establishing shot generated as video for motion, cheaper/simpler coverage shots left as static images. `ShotMediaSelection` is a list, so this is the natural, no-extra-concept case, not a third code path — "hybrid" is simply "some shots selected video, some not, some unselected."

The Execution Engine never sees `ShotMediaSelection` at all — by the time a render happens, its only signal is whatever `TimelineClip.asset_type` the already-existing `_resolve_clip_asset` rule derived from which files actually exist on disk (§25.2). This keeps the hybrid decision a **Producer Studio input concern**, not an Execution Engine concern, matching §7's existing rule that the Execution Engine invents no content and only compiles what Producer Studio already decided.

### 25.4 Contracts (`shared_core/contracts/video_generation.py` — new, 20th contract module)

Mirrors `render.py`/`publish.py`'s established shape exactly: an `Options` input, a `Request` bundle, a process-outcome `Result`, an async `Status` poll type, and a separate verification `Report` — the same "process success is necessary but not sufficient" discipline that gates `VIDEO_RENDERED` and (designed) `PUBLISHED`. **Credentials are never a field on any of these** — resolved live, inside `providers/google_veo.py` (and future provider modules) only, from `config.py`/environment, never logged, serialized, or written to any package file or report — the exact rule §24.3 already established for the Publishing Engine.

| Contract | Mirrors | Shape |
|---|---|---|
| `VideoGenerationOptions` | `RenderOptions` / `PublishOptions` | `provider: str = "google_veo"`, `aspect_ratio: str = "9:16"`, `resolution: Optional[str] = None` (defer to provider default), `seed_image_path: Optional[str] = None` (optional image-to-video conditioning — e.g. seeding from an already-generated `ImageAsset` for character/environment consistency), `dry_run: bool = False`, `timeout_seconds: Optional[int] = None`, `poll_interval_seconds: int = 10`, `max_poll_attempts: int = 60`. |
| `ProviderInfo` | `FFmpegInfo` / `PlatformInfo` | `provider: str`, `available: bool`, `account_label: Optional[str] = None` (never a token), `detail: Optional[str] = None`. Never raises on its own; the controller decides whether unavailability is fatal. |
| `VideoGenerationRequest` | `RenderRequest` / `PublishRequest` | `shot_prompt: ShotPrompt` (reuses the existing contract — the only field it needs is `video_motion_prompt`, already produced), `scene_id: int`, `shot_id: int`, `output_dir: str`, `options: VideoGenerationOptions`. |
| `VideoAsset` | `ImageAsset` (`agents/image_generator/contract.py`) | `asset_id`, `scene_id`, `shot_id`, `file_path`, `prompt_used`, `provider: str`, `external_job_id: Optional[str] = None`, `duration_seconds: Optional[float] = None`, `generated_at`. |
| `VideoGenerationStatus` | *(new async-poll shape, same role as `PublishingPlatform.check_status`'s return, §24.2)* | `status: str` (`"pending" \| "generating" \| "succeeded" \| "failed"`), `external_job_id: str`, `progress_pct: Optional[float] = None`, `detail: Optional[str] = None`. |
| `VideoGenerationResult` | `RenderResult` / `PublishResult` | `success: bool`, `dry_run: bool = False`, `provider: str = ""`, `scene_id: int`, `shot_id: int`, `external_job_id: Optional[str] = None`, `started_at`/`finished_at: Optional[datetime]`, `retry_count: int = 0`, `error: Optional[str] = None`, `error_type: Optional[str] = None` (`"generation_failed" \| "auth_failed" \| "timeout" \| "quota_exceeded" \| "content_filtered"`). `success=True` means only the provider *accepted and completed* the job — process diagnostics, not verified media quality. |
| `VideoGenerationValidationReport` | `RenderValidationReport` / `PublishValidationReport` | `is_valid: bool`, `checks: List[...]`, `probed: Optional[ProbedMedia]` (**reuses `shared_core.contracts.render.ProbedMedia` directly** — a generated clip and a rendered clip are probed the same way), `output_path: str`, `generated_at`. **This is the only thing that gates a shot's clip being trusted** — same role `RenderValidationReport.is_valid` plays for `VIDEO_RENDERED` (§7, §9). |
| `ShotMediaSelection` | *(new — §25.3)* | `scene_id: int`, `shot_id: int`, `mode: str` (`"image" \| "video"`). |
| `VideoGenerationManifest` | *(new — project-level record, Production Package's `video_manifest.json`, requirement 5)* | `manifest_id`, `source_prompt_set_id`, `selections: List[ShotMediaSelection]`, `assets: List[VideoAsset]`, `generated_at`. |

`PromptSet` and `ShotPrompt` (`shared_core/contracts/prompt_set.py`) are **not modified** — `video_motion_prompt` already exists and is consumed read-only, the same way the Execution Engine already treats every Producer Package artifact as read-only input (§7).

### 25.5 Provider Abstraction

A single abstract interface, `VideoGenerationProvider`, implemented once per external provider — the controller and every contract are written against this interface only, mirroring `PublishingPlatform` (§24.2) exactly:

| Method | Purpose |
|---|---|
| `authenticate() -> ProviderInfo` | Resolve credentials and confirm they're valid. Mirrors `ffmpeg_detector.detect_ffmpeg` / `PublishingPlatform.authenticate` — reports availability as data, never raises itself. |
| `generate(request: VideoGenerationRequest) -> VideoGenerationResult` | Submit the job and own everything the submission implies internally: most video providers are asynchronous (submit → poll → download), so retry/backoff and the poll loop both live inside this call, not the controller. |
| `check_status(external_job_id: str) -> VideoGenerationStatus` | Poll for async completion — same shape and same role as `PublishingPlatform.check_status`. |

`provider_registry.py` is a pure `{name: Type[VideoGenerationProvider]}` lookup (`resolve_provider(name) -> Type[VideoGenerationProvider]`, raising `VideoGenerationInputError` for an unknown name) — mirroring `publishing_engine/platforms/registry.py` (§24.2) exactly. **In this design, the registry is empty: zero providers are implemented.** Adding Google Veo, Runway, Kling, Luma, or Pika each means writing one new class implementing `VideoGenerationProvider` and adding one registry entry — zero changes to the controller, the contracts, or any other provider's code, the identical mechanism §24.2 already established for publishing platforms.

**Google Veo is the intended first, and design-only-designated, implementation** (`providers/google_veo.py`) — named because it is the provider the milestone brief calls out, not because any code, prompt template, or API contract for it has been written. No file under `providers/` is created by this design pass.

### 25.6 Module Layout (`video_generation_engine/`)

| Module | Role | Layer |
|---|---|---|
| `controller.py` (`VideoGenerationEngineController`) | Orchestrates the sequence in §25.8; the only place that decides whether to generate at all (`--dry-run` skips submission and postflight entirely, here — never inside a provider adapter, same rule §7/§24 already apply). | orchestration |
| `preflight.py` (`verify_generation_inputs`) | Confirms the target `media/video/` output directory is writable, confirms the requested shot(s) actually have a `video_motion_prompt` in the loaded `PromptSet`, and confirms `seed_image_path` (if given) still exists — the same "planning approved it, but I/O is real" justification §7's and §24's own `preflight.py` already use. | boundary (read-only) |
| `request_builder.py` (`build_generation_request`, `validate_generation_request`) | Pure: resolves `ShotMediaSelection` against `PromptSet` and assembles the typed `VideoGenerationRequest` per selected shot. | pure |
| `prompt_builder.py` (`build_video_prompt`) | Pure: composes the final provider-ready prompt string from `ShotPrompt.video_motion_prompt` + shot description + camera angle/movement + duration + aspect ratio — the video-generation analogue of `agents/image_generator/contract.py`'s existing `build_image_prompt`, same composition pattern, new function. | pure |
| `providers/base.py` | `VideoGenerationProvider` abstract interface (§25.5). | interface |
| `providers/google_veo.py` | Not created in this milestone — reserved name for the first real implementation (§25.5). | boundary (real network I/O), future |
| `provider_registry.py` (`resolve_provider`) | Pure name → implementation lookup (§25.5); empty in this design. | pure |
| `postflight.py` (`validate_generated_clip`) | Pure: compares a downloaded clip's `ProbedMedia` against the request's expected profile (duration, aspect ratio), producing `VideoGenerationValidationReport`. An unprobeable file is an unconditional failure, mirroring `postflight.validate_render`'s handling of a `None` probe. | pure |
| `errors.py` | `VideoGenerationError` hierarchy (§25.9). | — |

**Probing is intentionally *not* shared with `execution_engine.ffprobe_client`.** Reusing that function directly would create a new cross-engine import edge that doesn't exist anywhere else in the system — `execution_engine/` and `publishing_engine/` don't import each other either (§24.3 treats `video.mp4` as an opaque, already-finished file rather than re-probing it). This design accepts the small duplication of a thin `ffprobe`-invoking wrapper inside `video_generation_engine/` instead, preserving the "no engine imports another engine" symmetry that already holds for all of §7/§19/§24. (This mirrors the exact tradeoff already made once: `execution_engine/errors.py`'s `MediaAccessError` *was* reused by the Publishing Engine design, §24.7 — reuse is fine for a shared *type*, but a shared *boundary call* between peer engines is the line this design chooses not to cross, since it's a new dependency edge rather than a shared vocabulary.)

**Note on the milestone brief's suggested `contracts.py`:** the suggested example structure lists a `contracts.py` file inside `video_generation_engine/`. This design deliberately omits it, for consistency with the Publishing Engine precedent: §24.4's module table has no `contracts.py` either, because the actual contract *definitions* belong in `shared_core/contracts/` (§8, §19 — "Shared Core contains everything genuinely provider-agnostic... nothing in Shared Core may import from `director_studio/`, `producer_studio/`, `execution_engine/`, or `project_manager/`"), and every other module here imports them directly from `shared_core.contracts.video_generation` rather than through a redundant local re-export layer.

### 25.7 Pipeline Integration

```
Story Planner ──► Scene Planner ──► Shot Planner ──► Camera Planner
      ──► Character/Environment Bibles ──► Prompt Intelligence
             ──► PromptSet (image_prompt + video_motion_prompt per shot — ALREADY PRODUCED TODAY)
                    │
                    ├── media/images/  ◄── human, or opt-in agents/image_generator/ (UNCHANGED, §5)
                    │
                    └── media/video/   ◄── human, OR [NEW] Video Generation Engine
                                             (ShotMediaSelection picks which shots;
                                              provider generates scene_<id>_shot_<id>.mp4)
                    │
                    ▼
             Asset Validation (UNCHANGED) ──► ValidatedAssetManifest (image_path and/or video_path per shot)
                    ▼
             Timeline Planning (UNCHANGED) ──► prefers video over image per shot when both exist (§25.2, already shipped)
                    ▼
             Subtitle / Music / Editing / Thumbnail / Publishing Metadata Planning (UNCHANGED)
                    ▼
             FFmpeg Execution Engine (UNCHANGED) ──► video.mp4 (mixed image+video sources, already-shipped filter graph)
```

This directly answers the milestone's requested "Future" pipeline (`Story → Video Prompts → AI Video Provider → MP4 Clips → FFmpeg`): every arrow in that chain already exists except one — "AI Video Provider" — which is exactly and only what `video_generation_engine/` adds. It slots in as an **alternative, automatable populator of `media/video/`**, parallel to (never replacing) the permanent human checkpoint §1 already establishes between Director Studio and Producer Studio.

### 25.8 Execution Sequence (`VideoGenerationEngineController.run`)

1. Load the project; require `status in (PACKAGE_READY, MEDIA_IMPORTED, EDIT_PLAN_READY)`.
2. Load `PromptSet` (`video_prompts.json`) and the requested `ShotMediaSelection` list (explicit argument or a persisted `video_manifest.json` from a prior partial run).
3. For shots already carrying a valid `VideoAsset` from a prior run, **skip by default** — the same idempotency guard §24.5 designs for Publishing, adapted from "don't double-upload" to "don't double-spend": a routine re-run never silently regenerates (and re-charges for) an already-succeeded clip. Regenerating a specific shot is an explicit, targeted request, never the default of a bare re-run.
4. Validate the request (`request_builder.validate_generation_request`) and confirm generation inputs (`preflight.verify_generation_inputs`).
5. Resolve the provider adapter (`provider_registry.resolve_provider`) and authenticate (`provider.authenticate()` — a `VideoGenerationEnvironmentError` if credentials are missing/invalid or no provider is registered for the requested name; the one hard environment gate, same role `ffmpeg_detector`/`platform.authenticate()` play in §7/§24).
6. **`--dry-run` stops here** — returns the built `VideoGenerationRequest`(s) plus `VideoGenerationResult(success=True, dry_run=True)` per shot, nothing submitted, nothing persisted. Lives in the controller, never inside a provider adapter, for the same reason §7/§24 keep this branch at the orchestration layer.
7. Generate (`provider.generate(...)`) per selected shot — submission, polling, and download all happen inside this call (§25.5).
8. If generation succeeded, probe the downloaded clip and validate it (`postflight.validate_generated_clip`); if generation failed, there is nothing to probe.
9. Persist via `ProjectManager.save_video_generation_result` (§25.10) — writes the clip's `VideoAsset` into `video_manifest.json` and updates the project's generation-progress sub-fields. This step **never** advances `project.status` on its own — Asset Validation (unchanged, §6) remains the sole gate that advances state to `MEDIA_IMPORTED`, exactly as if a human had placed the same file by hand.

**Sequence diagram** (one shot, non-dry-run happy path; the skip/dry-run/failure branches above are noted inline):

```mermaid
sequenceDiagram
    participant UI as Dashboard / CLI
    participant Ctl as VideoGenerationEngineController
    participant PM as ProjectManager
    participant Pre as preflight / request_builder
    participant Reg as provider_registry
    participant Prov as VideoGenerationProvider (e.g. google_veo)
    participant Ext as External Provider API
    participant Post as postflight

    UI->>Ctl: run(project_id, selections, options)
    Ctl->>PM: load_project(project_id)
    PM-->>Ctl: Project
    Ctl->>PM: load_prompt_set()
    PM-->>Ctl: PromptSet
    Ctl->>Ctl: filter shots already carrying a valid VideoAsset (skip by default, step 3)
    Ctl->>Pre: validate_generation_request / verify_generation_inputs
    Pre-->>Ctl: VideoGenerationRequest (or VideoGenerationInputError)
    Ctl->>Reg: resolve_provider(options.provider)
    Reg-->>Ctl: VideoGenerationProvider class
    Ctl->>Prov: authenticate()
    Prov-->>Ctl: ProviderInfo

    alt dry_run = true
        Ctl-->>UI: VideoGenerationResult(success=True, dry_run=True) — nothing submitted, nothing persisted
    else dry_run = false
        Ctl->>Prov: generate(VideoGenerationRequest)
        Prov->>Ext: submit generation job
        Ext-->>Prov: external_job_id
        loop poll until succeeded / failed / max_poll_attempts
            Prov->>Ext: check_status(external_job_id)
            Ext-->>Prov: VideoGenerationStatus
        end
        alt status = succeeded
            Prov->>Ext: download clip
            Ext-->>Prov: clip bytes
            Prov-->>Ctl: VideoGenerationResult(success=True)
            Ctl->>Post: validate_generated_clip(clip, request)
            Post-->>Ctl: VideoGenerationValidationReport
        else status = failed / timeout
            Prov-->>Ctl: VideoGenerationResult(success=False, error_type=...)
            Note over Ctl,Post: nothing to probe — postflight is skipped
        end
        Ctl->>PM: save_video_generation_result(VideoAsset?, VideoGenerationResult, VideoGenerationValidationReport?)
        PM->>PM: write video_manifest.json; update video_generation_manifest_path / video_generation_status
        Note over PM: project.status is never advanced here — Asset Validation remains the sole MEDIA_IMPORTED gate
        Ctl-->>UI: VideoGenerationResult (+ VideoGenerationValidationReport)
    end
```

### 25.9 Errors

`video_generation_engine/errors.py` mirrors `execution_engine/errors.py` and `publishing_engine/errors.py` exactly — raised only for problems discovered before generation can even be attempted; everything that happens once a provider call is actually made is a `VideoGenerationResult`, never an exception:

- `VideoGenerationError` — base.
- `VideoGenerationEnvironmentError` — credentials missing/invalid, or the configured provider has no registered adapter.
- `MediaAccessError` — *(reused from `execution_engine/errors.py`, same reuse `publishing_engine`'s design already makes, §24.7 — same failure concept, no reason for a third class)* — the seed image (if given) or output directory is missing/unwritable.
- `VideoGenerationInputError` — `PromptSet` missing the requested shot, or `ShotMediaSelection` references a `scene_id`/`shot_id` that doesn't exist in the plan.

### 25.10 State & Output Specification

**No new top-level `ProjectState`** (§25.1, rule 4). New `Project` sub-fields (all `Optional`, mirroring `rendered_video_path`'s own pattern): `video_generation_manifest_path: Optional[str] = None`, `video_generation_status: Optional[str] = None` (`"not_started" | "in_progress" | "partial" | "complete"`, a coarse dashboard-facing summary only — the authoritative per-shot detail lives in `video_manifest.json` itself). Because every new field is `Optional` with a `None` default, an old project's `project.json` — which has never heard of these keys — deserializes exactly as it does today; this is the same mechanism that already made `rendered_video_path`, `external_video_id`, etc. migration-free additions.

**Output specification** — written by `project_manager/video_generation_writer.py` into the Production Package, alongside the already-existing `video_prompts.json` (§10):

| File | Written by | When | Contents |
|---|---|---|---|
| `video_manifest.json` | `video_generation_writer.write_video_generation_manifest` | Every attempted (non-dry-run) generation run, updated incrementally as shots complete. | `VideoGenerationManifest`: every shot's `ShotMediaSelection`, its resulting `VideoAsset` (if succeeded), and the `VideoGenerationResult`/`VideoGenerationValidationReport` pair for diagnostics — the same process-vs-verification split as `render_report.json`/`render_validation.json` (§12) and `publish_report.json`/`publish_validation.json` (§24.8). |

The actual clip files land in `projects/<project_id>/media/video/scene_<id>_shot_<id>.mp4` — **the exact path and naming convention Asset Validation already expects from a human** (§6, §14) — so no change to `agents/asset_validator/*`, `producer_package_writer.py`, or any Producer Package file is required.

**Note on the milestone brief's suggested `video_prompts/shot001.txt` layout:** the brief's example shows one prompt file per shot. This design deliberately does not introduce that layout — `production-package/video_prompts.json` (the serialized `PromptSet`) already carries every shot's `video_motion_prompt` in one place, is already written today (§25.2), and is the only input `request_builder.py` needs. Adding a parallel per-shot `.txt` layout would be a second, redundant source of the same data with no consumer designed to read it — the milestone's underlying need ("a durable, inspectable record of what was asked for, per shot") is already met by `video_prompts.json` plus `video_manifest.json`'s `selections`/`assets` lists.

`ProjectManager` additions: `load_prompt_set` (already exists, reused), `get_media_video_dir` (hands out `media/video/`'s location, mirroring `get_images_dir`), `save_video_generation_result` (writes `video_manifest.json`, updates the `Project` sub-fields — never advances `status`).

### 25.11 Dashboard Support

No UI is implemented by this design; the shape below is what a future implementation milestone would build against, consuming the same typed contracts (§25.4) the backend already exposes via a new router mirroring the existing `web_api/routers/publish.py`/`render.py` shape (trigger + status-poll, not a new API convention).

- **Media Generation Mode** — a project-level choice, presented once (e.g. on `ProjectWorkspace`'s `OverviewTab` or `MediaTab`, both already existing): **Image Mode** (today's default, unchanged), **Video Mode** (every shot defaults to `"video"` in `ShotMediaSelection`), **Hybrid Mode** (per-shot toggle, defaulting to `"image"`). This is a UI convenience over `ShotMediaSelection` (§25.3) — the backend has no separate "mode" concept beyond the per-shot list.
- **`MediaTab.tsx`** (already existing, already shows per-shot media coverage) gains a per-shot IMAGE/VIDEO toggle plus a "Generate" action and a status chip reflecting `VideoGenerationStatus`/`video_generation_status`, polled the same way `features/runs/LiveStatusPanel.tsx` and `RunControls.tsx` already poll long-running producer/render runs today — reusing that existing polling pattern rather than inventing a second one for this async operation.
- **A pre-generation cost/consent confirmation** is a required UI step before any provider call — unlike the opt-in `image_generator` (fast, cheap, synchronous), video generation is slow and has real per-clip cost; the dashboard must never trigger it silently as a side effect of another action.
- **`RenderPreviewTab.tsx`** (already existing) needs no change — it previews the already-unchanged Execution Engine output, which already treats mixed image/video sources uniformly (§25.2).

### 25.12 Migration & Backward Compatibility

Requirement 9 ("old project format must continue working, zero migration") is satisfied structurally, not by a migration script:

- No existing contract (`PromptSet`, `ShotPrompt`, `ValidatedAsset`, `TimelineClip`, `EditingSegment`, `Project`) is modified — only new, fully `Optional` fields/files are added.
- `video_manifest.json` and the new `Project` sub-fields are absent from every old project; their absence is a valid, already-handled state (`video_generation_status: None` reads as "never attempted," identical in meaning to a project that never runs this engine at all).
- The Video Generation Engine is opt-in at the CLI/API layer, the same way `--generate-images` is opt-in today (§5) — it is never invoked as part of `DirectorStudioController.run` or `ProducerStudioController.run`'s default sequencing.
- Asset Validation, Timeline Planning, Editing Planning, and the Execution Engine require **zero code changes** (§25.2) — they already handle a project with only images, only videos, or a mix, per shot.

### 25.13 Risks

1. **Cost and latency are qualitatively different from the existing `image_generator` tool.** A synchronous, cheap per-scene image call becomes an asynchronous, potentially multi-minute, real-money-per-clip operation per *shot*. Mitigation: opt-in by default (§25.3, §25.12), explicit dashboard consent (§25.11), the idempotency guard against silent re-spend (§25.8 step 3), and `dry_run` support at every layer (§25.8 step 6).
2. **Visual inconsistency across shots.** Unlike Director Studio's Character/Environment Bibles (consumed today by `image_generator` indirectly via prompt text), an external video provider has no innate access to a project's established visual identity. Mitigation: `prompt_builder.build_video_prompt` (§25.6) composes the full character/environment/camera context into the prompt exactly as `build_image_prompt` already does, and `VideoGenerationOptions.seed_image_path` (§25.4) allows image-to-video conditioning from an already-approved `ImageAsset` for shots where consistency matters more than motion variety.
3. **Provider capability variance.** Not every provider supports async polling, image-to-video seeding, or the same aspect ratios; `VideoGenerationProvider` (§25.5) may need capability flags on `ProviderInfo` once a second real provider is implemented (deferred, §25.15) — the abstraction is not guaranteed leak-proof until proven against two providers, not one.
4. **Partial-failure UX.** A hybrid-mode project can end up with some shots generated, some pending, some failed. Asset Validation's existing `missing_shot` tolerance (up to `MAX_TOLERATED_MISSING_SHOTS`) already handles a shot with no media at all gracefully, but the dashboard (§25.11) must surface *why* a shot is missing (never attempted vs. failed vs. still generating) rather than presenting all three identically.
5. **Rendered-file memory profile is unverified, not just assumed safe.** This codebase has direct, recent, hard-won history here (`RenderOptions`'s own docstring, and the last several commits: "segmented render fallback for many-scene projects — fixes OOM", "delete segmented-render intermediates as they're consumed") — a "should be fine" assumption about ffmpeg memory behavior has already been *wrong* once in this exact codebase, under real production RSS telemetry. A generated H.264/H.265 video source has a materially different decode memory profile than looping a static image (§25.14) and must not be assumed safe by analogy — see §25.14's recommended verification step before this ships behind any real provider.

### 25.14 Memory & Storage Considerations

- **Memory:** `filter_graph_builder.py` already normalizes image and video inputs through the same `trim`/`normalize`/`concat`/`xfade` graph (§25.2), so no *new* filter-graph code path is introduced by this milestone. However, decoding a real video source is not the same operation as looping a static image (`-loop 1`), and this repository's own render-pipeline history (`RenderOptions.preset`/`.threads` docstrings, the segmented-renderer OOM fix) shows that "the code path is unified" has previously been mistaken for "the memory cost is unified." **Before any real provider ships (V3+, §25.15), a real multi-scene render mixing generated video clips should be memory-profiled under the same production-RSS-telemetry methodology already used for the image-only case**, and `should_segment`'s segmentation threshold (`execution_engine/segmented_renderer.py`) revisited if video sources push peak RSS higher than images did at the same scene count. This is a **testing/verification recommendation for a future milestone, not a design change** — no code is touched here.
- **Storage:** generated clips are dramatically larger than generated images (tens of MB vs. low single-digit MB each), and hybrid/video-mode projects with multiple re-rolled shots multiply that further. `media/` is already outside version control (human-imported assets are never committed) and the project already has a working pattern of aggressively deleting consumed intermediates (`fix(render): delete segmented-render intermediates as they're consumed`) — the same discipline should extend to superseded/failed generation attempts in `media/video/`, so a shot re-rolled three times doesn't leave two orphaned clips behind. This is a `video_generation_writer`/cleanup-policy design note for the implementation milestone, not something this design pass builds.

### 25.15 Explicitly Deferred / Not Designed Yet

- **Google Veo's actual request/response shape, auth flow, and pricing model** — none of this is designed here; `providers/google_veo.py` is a reserved name, not a specification (§25.5).
- **A second real provider** (Runway/Kling/Luma/Pika) proving the registry abstraction generalizes, and any capability-flag additions to `ProviderInfo` that proving exercise surfaces (§25.13, item 3).
- **Automatic mode selection** (e.g. "generate video only for the establishing shot of each scene") — v1 `ShotMediaSelection` is always an explicit, human/dashboard-driven list; no heuristic auto-selection is designed.
- **Budget/quota guardrails** (a project-level spend cap, a warn-before-N-clips confirmation) — flagged as a real need (§25.13, item 1) but not specified here; likely a `VideoGenerationOptions` addition in a later milestone.
- **Cleanup policy implementation** for superseded/failed clips (§25.14) — the need is identified, the mechanism is not designed.
- **Memory-profiling methodology details** (§25.14) — the recommendation to profile is recorded; the actual telemetry harness is not designed here.

### 25.16 Recommended First Implementation Milestone (V2)

This milestone (V1) is design-only, per its own constraints — no application code, no Google Veo integration, no API calls. Following the exact precedent already set by how the Execution Engine (§7) and Publishing Engine (§24) were actually built — structure and contracts first, a real external integration only once the skeleton is proven — the recommended scope for **V2** is:

**Build the skeleton with zero external providers, so the whole pipeline is provably correct before any real cost or network dependency exists:**

1. `shared_core/contracts/video_generation.py` — all contracts from §25.4, unit-tested for round-trip serialization only (no behavior).
2. `video_generation_engine/` module skeleton: `controller.py`, `preflight.py`, `request_builder.py`, `prompt_builder.py`, `providers/base.py` (the abstract `VideoGenerationProvider`), `provider_registry.py`, `postflight.py`, `errors.py` — implementing the full sequence in §25.8, including the diagram in this revision.
3. **One deterministic, zero-cost "local" provider** registered under a non-default name (e.g. `"local_stub"`), implementing `VideoGenerationProvider` by synchronously producing a short placeholder clip (e.g. via `ffmpeg -f lavfi -i color=...`, reusing the same black-frame technique `command_builder.py` already uses for missing shots, §3) instead of calling any real network API. This is what makes the milestone verifiable end-to-end — dry-run, happy-path generate, postflight validation, idempotent skip-on-rerun, and manifest persistence — without touching Google Veo or spending anything.
4. `project_manager/video_generation_writer.py` and the three `ProjectManager` additions listed in §25.10 (`get_media_video_dir`, `save_video_generation_result`), plus the new `Project` sub-fields.
5. CLI entry point mirroring `render_app.py`/the publishing CLI's shape, opt-in only, never part of `DirectorStudioController`/`ProducerStudioController`'s default sequencing (§25.12).

**Explicitly out of scope for V2** (deferred to V3+, per §25.15): the real `providers/google_veo.py` implementation, any second real provider, dashboard UI (§25.11 remains a design until a dedicated frontend milestone), budget/quota guardrails, the cleanup policy for superseded clips, and the memory-profiling exercise for mixed image/video renders (§25.14) — that profiling should happen once real (larger, provider-generated) clips exist to profile, not against the local stub's placeholder output.

This ordering keeps every milestone independently shippable and reversible — exactly as `render.py`'s and `publish.py`'s own history (§22) already demonstrates for this codebase — and means the first time a real API call to any video provider is made is a deliberate, isolated V3 decision, not a side effect of building the plumbing around it.

---

*This document is the frozen architecture. Deviations discovered during implementation should be raised as a proposed amendment to this document before being coded, not worked around silently.*

---

## Architecture Status

**Status:** FROZEN

**Version:** 2.2.0

**Last Updated:** 2026-08-02

Breaking changes require:
- Architecture review
- ADR (Architecture Decision Record)
- Migration plan

Minor implementation changes do not require architecture updates.
