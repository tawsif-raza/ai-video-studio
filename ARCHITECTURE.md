# AI Video Studio 
— Architecture

**Status:** Frozen / Approved
**Scope:** This document describes the **target architecture** — the system after migration is complete, not the current implementation. It is the single source of truth. Every future code change must align with it. Where the current codebase differs, the difference is tracked in [§15 Migration Roadmap](#15-migration-roadmap), not resolved by silently deviating from this document.

---

## 1. Project Vision

AI Video Studio is an **AI Production Planning Platform**, not an AI media generator.

Think of it as a movie production company split into two studios:

- **Director Studio** acts like the film director. It researches, writes the story, breaks it into scenes and shots, designs characters and environments, plans camera movement, and writes prompts. Its output is a complete **Production Package**.
- **Producer Studio** acts like the film producer. It takes a Production Package plus media the human has generated with their own preferred tools, validates it, builds a timeline, plans subtitles and music, creates an editing plan, and assembles the final video with FFmpeg.

Between the two studios sits a deliberate, permanent human step: **the human generates the actual images, video, and voice** using whatever tools they prefer — Gemini, Veo, Flux, Midjourney, ElevenLabs, or anything else — and selects the best results. The AI's job in that step is finished the moment the Production Package is exported.

The platform's value is the *planning intelligence* — story structure, shot coverage, character/environment consistency, prompt quality, editing structure — not the pixels or audio themselves.

---

## 2. Design Philosophy

- **Planning, not generation.** No component in this system calls an image, video, or voice generation API as part of its core responsibility. The one exception (a manual, explicitly-invoked preview tool) is opt-in and never part of the default pipeline.
- **Tool-agnostic by construction.** Prompts and specs in the Production Package are written to work with any external generative tool, not tuned to one vendor.
- **Single responsibility per agent.** Every planner does exactly one job, consumes one typed input contract, and produces one typed output contract. An agent that starts doing two things is a signal to split it. Voice Script and Prompt Intelligence, for example, both write text into the package, but narration and shot-prompt composition are different skills with different inputs and different validation rules — they stay separate agents rather than merging into one.
- **Contracts over conversation.** Agents never pass ad hoc dicts to each other. All inter-agent data exchange happens through typed Pydantic contracts, validated at the boundary.
- **Two-layer validation.** Every LLM output passes through *shape* validation (does the JSON match the schema?) and *business* validation (is the content actually correct — right scene coverage, right duration, no orphaned references?). Shape validation alone is not enough for an unsupervised LLM pipeline.
- **Projects, not files.** All work is organized around a persistent **Project**, not disconnected UUID-stamped JSON files in a flat folder. A Project is the unit of storage, versioning, and resumability — and **Project Manager** (§4) is its sole gatekeeper: neither studio ever touches a filesystem, database, or object store directly.
- **What a thing is, and how it's written, are different concerns.** Shared Core defines the typed shape of the Production Package and Producer Package. Project Manager owns turning those typed objects into files. An agent producing a `CharacterBible` doesn't know or care whether it ends up as JSON on a laptop or a row in Postgres.
- **Incremental evolution.** The architecture evolves by refactoring and extending working code, not by rewriting. Existing agents, contracts, and validators are the foundation being built on, not scaffolding to discard.
- **The human checkpoint is a feature, not a gap.** The hard boundary between Director Studio's output and Producer Studio's input is intentional — creative media selection is a human decision that no agent should make on the user's behalf.

---

## 3. High-Level Architecture

```
User / CLI / Future UI
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│                       Project Manager                      │
│  creation · loading · saving · manifests · metadata ·      │
│  package export · lifecycle & state management              │
└───────────┬───────────────────────────────┬───────────────┘
            │ invokes, receives              │ invokes, receives
            │ typed results only             │ typed results only
            ▼                                ▼
  ┌───────────────────┐            ┌───────────────────┐
  │  Director Studio    │            │  Producer Studio    │
  │  (planning only,    │            │  (assembly only,    │
  │   zero file I/O)    │            │   zero file I/O*)   │
  └──────────┬─────────┘            └──────────▲──────────┘
             │                                  │
             ▼                                  │
   ┌───────────────────┐              ┌───────────────────┐
   │ Production Package  │───HUMAN────▶│ Human-imported      │
   │ (serialized by      │  generates  │ media (validated     │
   │  Project Manager)   │  media      │  by Project Manager) │
   └───────────────────┘              └───────────────────┘
```
*_FFmpeg Export is the one sanctioned exception — see §6._

Dependency layering:

```
┌───────────────────────────────────────────────────┐
│                    Shared Core                      │
│  BaseAgent · Package Schemas · LLM Clients · Models  │
│  · Utils · Config · Exceptions                        │
└───────────────────────┬───────────────────────────┘
                         │
                         ▼
              ┌───────────────────────┐
              │     Project Manager     │
              │ (persistence, lifecycle,│
              │  package serialization) │
              └──────────┬─────┬───────┘
                    invokes│    │invokes
                         ▼      ▼
              ┌──────────────┐ ┌──────────────┐
              │ Director      │ │ Producer      │
              │ Studio        │ │ Studio        │
              └──────────────┘ └──────────────┘
```

**Note on direction:** the vision-level chain (Shared Core → Project Manager → Director Studio → Production Package → Producer Studio) describes control and data flow, not Python import direction. Import direction runs the other way for invocation: `project_manager` imports and calls into `director_studio` and `producer_studio` to run stages; neither studio imports `project_manager`, imports the other studio, or touches storage — they only accept typed arguments and return typed results. This is what makes "studios never perform filesystem operations directly" a structural guarantee enforced by module boundaries, not just a convention (see §14).

---

## 4. Project Manager Architecture

**Responsibility:** Project Manager is the sole owner of persistence and lifecycle state. It sits between the user-facing entry point (CLI today, a future Web/Desktop UI later) and both studios. Neither studio ever touches the filesystem, a database, or object storage directly — they receive typed inputs from Project Manager and return typed outputs to it.

Project Manager owns:

- **Project creation** — allocate a new project id, initialize `project.json`, set state to `CREATED`.
- **Loading** — reconstruct a Project, and whichever typed stage results already exist, from storage.
- **Saving** — persist a stage's typed output against the project.
- **Manifests** — maintain `manifest.json` inside the Production Package, and the equivalent index for the Producer Package, as the record of what exists and its status.
- **Metadata** — maintain `project.json` and the package-level `metadata.json` — target duration, art style, aspect ratio, language, model(s) used, timestamps.
- **Package exporting** — serialize a project's typed stage outputs into the on-disk Production Package / Producer Package layout, using the schema Shared Core defines (§7). Project Manager owns *how* a package is written; Shared Core owns *what* it is.
- **Project lifecycle / state management** — own the state machine (§8) and its transition rules; decide, given a project's current state, which stage and which studio runs next.

Project Manager invokes Director Studio or Producer Studio for a given stage, receives a typed `AgentResult` back, and is the only component that then writes anything to disk. Director Studio and Producer Studio contain no file I/O of any kind — not even reads — with the single named exception in §6.

Project Manager is deliberately **not** part of Shared Core (§7): it depends on Shared Core, but it owns stateful, application-specific lifecycle logic — not a stateless, reusable primitive.

---

## 5. Director Studio Architecture

**Responsibility:** planning only. Director Studio never generates media and never calls a media-generation API as part of its default flow. It also performs no filesystem I/O of its own — Project Manager supplies its inputs and persists its outputs.

### Workflow

```
Research
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
Prompt Intelligence
   ↓
Voice Script
   ↓
Production Package Export
```

- Each stage is one agent following the standard agent pattern (§14).
- The **DirectorStudioController** receives the project's current typed state from Project Manager, runs the next stage whose inputs are ready, and returns the typed result to Project Manager — it never loads, persists, or touches project state itself.
- Any stage can be re-run in isolation against an existing project (e.g. regenerate Character Bible without re-running Story Planning); Project Manager decides when a re-run is needed, based on the state machine (§8) and which upstream inputs have changed.
- Director Studio's terminal contribution is returning every planning stage's typed output to Project Manager. Project Manager then exports/finalizes the **Production Package** (§9) and marks the project `PACKAGE_READY`. Director Studio itself never writes the package.

---

## 6. Producer Studio Architecture

**Responsibility:** assembly and publishing planning, plus final video export. Producer Studio never plans story content and never edits creative decisions made by Director Studio — it only works with what the Production Package and the human-supplied media give it. Like Director Studio, it performs no filesystem I/O of its own, with one named exception below.

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
Editing Plan
   ↓
Thumbnail Prompt
   ↓
Publishing Metadata
   ↓
FFmpeg Export
```

- **Input:** typed data Project Manager assembles for it — the Production Package's contents, plus a manifest of human-imported media (images, video clips, voice audio) that Project Manager has already confirmed exists in the project's `media/` directory.
- The **ProducerStudioController** sequences these agents the same way DirectorStudioController does — it receives typed inputs from Project Manager, runs the next stage, and returns a typed result. It never reads or writes a file itself.
- Asset Validation is the entry gate: it checks that imported media actually covers what the Production Package expects (one image/video per shot or scene, audio present, correct formats) before any planning proceeds — analogous to how Director Studio's validators catch structurally-valid-but-wrong LLM output.
- **FFmpeg Export is the one sanctioned exception to "no filesystem I/O."** It reads source media and writes the rendered video file, using paths Project Manager supplies — it never decides its own paths, and it never touches `manifest.json`, `metadata.json`, or `project.json`. Those remain exclusively Project Manager's. It is intentionally the last step and isolated in its own module so its failure modes (missing binary, codec issues) don't contaminate the planning agents above it.
- **Output:** typed results (Timeline, Subtitles, MusicPlan, EditingPlan, thumbnail prompt, publishing metadata) returned to Project Manager, which serializes them into the project's `producer-package/` and, after FFmpeg Export, the rendered video into `exports/`.

---

## 7. Shared Core Responsibilities

Shared Core contains everything that is genuinely provider-agnostic and studio-agnostic, stateless, and reusable. Nothing in Shared Core may import from `director_studio/`, `producer_studio/`, or `project_manager/`.

| Component | Responsibility |
|---|---|
| `BaseAgent` + exceptions | The universal agent contract: `build_prompt → call LLM with retry → validate schema → validate business rules → produce public contract`. Every planner in both studios inherits this. |
| `AgentResult` / `AgentMetadata` | Generic success/failure envelope returned by every agent run. |
| **Package Schemas** | Typed Pydantic models defining the shape of every file in the Production Package and the Producer Package — **what a package is.** Every agent's public output contract is (or maps directly onto) one of these types. Project Manager owns serializing instances of these types to disk (§4, §9) — **how a package is written** — Shared Core only defines their shape. |
| LLM Clients (Gemini / GPT / Groq) | Interchangeable text-generation clients sharing one `.generate()` interface. Studio code never talks to a provider SDK directly. |
| `utils` (`json_utils`, `logger`) | JSON extraction from raw LLM text; consistent structured logging. |
| Shared lookups | Cross-referencing helpers (e.g. resolving which environment profile belongs to which scene) used by controllers in either studio. |
| Base config primitives | API keys, retry defaults, temperature defaults, log level — settings with no opinion about which studio is running. |

Explicitly **not** in Shared Core:

- **Project Manager** (§4) — it depends on Shared Core but owns stateful, application-specific lifecycle logic, not a reusable primitive.
- Studio-specific config overlays (feature flags, per-studio behavior).
- Any individual agent.
- The serialization/writing logic for either package — that's Project Manager's job. Shared Core only defines the shape being written.

---

## 8. Project Lifecycle

A **Project** is the single persistent unit of work, owned end-to-end by **Project Manager** (§4). Everything else — Production Package, imported media, Producer Package, final export — nests inside a Project.

### End-to-End Flow

```
User
    │
    ▼
Create Project
    │
    ▼
Research
    │
    ▼
Story Planning
    │
    ▼
Scene Planning
    │
    ▼
Shot Planning
    │
    ▼
Camera Planning
    │
    ▼
Character Bible
    │
    ▼
Environment Bible
    │
    ▼
Prompt Intelligence
    │
    ▼
Voice Script
    │
    ▼
Production Package
    │
    ▼
Human generates media
    │
    ▼
Producer Studio
    │
    ▼
Asset Validation
    │
    ▼
Timeline
    │
    ▼
Subtitles
    │
    ▼
Editing Plan
    │
    ▼
FFmpeg Export
    │
    ▼
Final Video
```

This is the simplified headline view. The full Producer Studio stage list (§6) also includes Music Planning, Thumbnail Prompt, and Publishing Metadata between Subtitles and FFmpeg Export — omitted here for readability, not dropped from the architecture.

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
PUBLISHED
```

| State | Set by | Meaning |
|---|---|---|
| `CREATED` | Project Manager | Project scaffold allocated; no stages run yet. |
| `RESEARCHED` | Director Studio | Research stage returned a validated ResearchBrief. |
| `STORY_COMPLETE` | Director Studio | Story Planner returned a validated ProductionPlan. |
| `SCENES_COMPLETE` | Director Studio | Scene Planner returned a validated Storyboard. |
| `SHOTS_COMPLETE` | Director Studio | Shot Planner returned a validated ShotPlan. |
| `CAMERA_COMPLETE` | Director Studio | Camera Planner returned a validated CameraPlan. |
| `CHARACTERS_COMPLETE` | Director Studio | Character Planner returned a validated CharacterBible. |
| `ENVIRONMENTS_COMPLETE` | Director Studio | Environment Planner returned a validated EnvironmentBible. |
| `PROMPTS_COMPLETE` | Director Studio | Prompt Intelligence **and** Voice Script have both returned validated output. |
| `PACKAGE_READY` | Project Manager | Production Package fully serialized and manifest written. Director Studio's job is done. |
| `MEDIA_IMPORTED` | Project Manager | Human has placed generated media into the project; Asset Validation has passed. |
| `EDIT_PLAN_READY` | Producer Studio | Timeline, Subtitles, Music Planning, Editing Plan, Thumbnail Prompt, and Publishing Metadata have all completed — everything needed to render is ready. |
| `VIDEO_RENDERED` | Producer Studio | FFmpeg Export has produced the final video file. |
| `PUBLISHED` | Project Manager | The human has published the rendered video externally (e.g. uploaded to YouTube) and confirmed it in the project. |

Voice Script keeps its own agent and its own typed output (§2, §12) — it simply doesn't get a dedicated top-level state of its own; its completion is folded into `PROMPTS_COMPLETE` alongside Prompt Intelligence, the same way Asset Validation/Timeline/Subtitles/Music Planning/Thumbnail Prompt/Publishing Metadata are folded into the `MEDIA_IMPORTED → EDIT_PLAN_READY` window. Finer-grained per-agent progress within a state, if ever needed, is tracked as a sub-field on the project record — not as additional top-level states — so the state machine always matches the ladder above exactly.

### Rules

- A Project is created once, with a stable id, and evolves in place. Re-running a stage updates that stage's output within the same project rather than creating a new disconnected artifact.
- Each stage's output records which inputs it was generated from (e.g. Character Bible records the plan version it was built against), so Project Manager can detect when a re-run is needed versus when cached output is still valid.
- **Project Manager is the only writer of project state and the only component with filesystem access.** Agents and studio controllers only ever hand typed data back to Project Manager — they never open a file themselves.
- Projects are self-contained: everything needed to resume work on a project — at any lifecycle stage, on any machine — lives inside that project's directory.

---

## 9. Production Package Specification

The Production Package's shape is defined once, in Shared Core, as a typed schema (§7). Project Manager serializes it to disk into `projects/<project_id>/production-package/`, following that schema — it is the complete, tool-agnostic handoff to the human. Director Studio's agents produce instances of these types; they never write the files themselves.

| File | Produced by | Contents |
|---|---|---|
| `story.md` | Story Planner | Human-readable story: title, logline, theme, tone, character list, scene list. |
| `scene_plan.json` | Scene Planner | Scene-level breakdown: setting, mood, characters present, estimated duration. |
| `shot_plan.json` | Shot Planner | Per-scene shot list: what happens in each shot, characters in shot, duration. |
| `camera_plan.json` | Camera Planner | Per-shot camera angle, movement, and coverage detail. |
| `character_bible.json` | Character Planner | One visual profile per character — build, face, hair, outfit, color palette, art-style keywords, reference prompt. |
| `environment_bible.json` | Environment Planner | One visual profile per unique setting — time of day, weather, key visual elements, color palette, lighting, reference prompt. |
| `image_prompts.json` | Prompt Intelligence | Final, polished image-generation prompt per shot, ready to paste into any tool. |
| `video_prompts.json` | Prompt Intelligence | Final motion/camera prompt per shot, for video generation tools. |
| `voice_script.txt` | Voice Script | Full narration/dialogue script in reading order. |
| `metadata.json` | Project Manager | Package-level metadata: project id, generation timestamps, target duration, art style, model(s) used. |
| `manifest.json` | Project Manager | Index of every file in the package with a short description and generation status — the entry point for anything (human or Producer Studio) consuming the package. |

Producer Studio's analogous deliverable — the **Producer Package**, written into `projects/<project_id>/producer-package/` — follows the identical pattern: its shape is defined in Shared Core alongside the Production Package schema, and Project Manager serializes it. It is specified alongside its workflow in §6 and §10; it is not part of the Production Package above since it's a different studio's output, generated after the human's media step.

---

## 10. Folder Structure

```
ai_video_studio/
├── app.py                          # thin CLI entrypoint — talks only to project_manager
│
├── shared_core/
│   ├── base_agent.py
│   ├── exceptions.py
│   ├── models.py                        # AgentResult, AgentMetadata
│   ├── config.py                        # provider-agnostic settings
│   ├── lookups.py                       # cross-agent reference helpers
│   ├── production_package_schema.py     # typed shape of the Production Package (§7, §9)
│   ├── producer_package_schema.py       # typed shape of the Producer Package (§7, §9)
│   ├── llm/
│   │   ├── gemini_client.py
│   │   ├── gpt_client.py
│   │   └── groq_client.py
│   └── utils/
│       ├── json_utils.py
│       └── logger.py
│
├── project_manager/
│   ├── config.py                   # storage location/layout — studios never read this
│   ├── project.py                  # Project model (id, name, state, timestamps)
│   ├── store.py                    # create / load / update / list a Project
│   ├── lifecycle.py                # state machine + transition rules (§8)
│   ├── package_writer.py           # serializes the Production Package to disk
│   └── producer_package_writer.py  # serializes the Producer Package to disk
│
├── director_studio/
│   ├── config.py                   # Director-specific overlay
│   ├── controller.py               # DirectorStudioController — pure stage execution, zero I/O
│   └── agents/
│       ├── research/
│       ├── story_planner/
│       ├── scene_planner/
│       ├── shot_planner/
│       ├── camera_planner/
│       ├── character_planner/
│       ├── environment_planner/
│       ├── prompt_generator/       # "Prompt Intelligence"
│       └── voice_script/
│           ├── agent.py
│           ├── contract.py
│           ├── schema.py
│           ├── prompt.py
│           └── validator.py
│
├── producer_studio/
│   ├── config.py                   # Producer-specific overlay
│   ├── controller.py               # ProducerStudioController — pure stage execution, zero I/O
│   ├── export/
│   │   └── ffmpeg_export.py        # sole sanctioned real-media I/O step (§6, §14)
│   └── agents/
│       ├── asset_validator/
│       ├── timeline_planner/
│       ├── subtitle_planner/
│       ├── music_planner/
│       ├── editing_plan/
│       ├── thumbnail_prompt/
│       └── publishing_metadata/
│
├── projects/
│   └── <project_id>/
│       ├── project.json            # project state, status, stage history — owned by Project Manager
│       ├── production-package/     # see §9
│       ├── media/                  # human-imported generated assets
│       │   ├── images/
│       │   ├── video/
│       │   └── audio/
│       ├── producer-package/       # timeline, subtitles, editing plan, publishing metadata
│       └── exports/
│           └── final_video.mp4
│
└── tests/
    ├── shared_core/
    ├── project_manager/
    ├── director_studio/
    ├── producer_studio/
    └── integration/
```

Every agent — in either studio — keeps the existing, proven five-file shape: `agent.py`, `contract.py`, `schema.py`, `prompt.py`, `validator.py`. This structure is not being replaced; it is being reused for every new planner in both studios.

---

## 11. Data Flow

### Director Studio (per project)

```
Project Manager loads project (or creates new)
      │
      ▼
Research ──► ResearchBrief
      │
      ▼
Story Planner ──► ProductionPlan
      │
      ▼
Scene Planner ──► Storyboard
      │
      ▼
Shot Planner ──► ShotPlan
      │
      ▼
Camera Planner ──► CameraPlan  (consumes ShotPlan)
      │
      ▼
Character Planner ──► CharacterBible
      │
      ▼
Environment Planner ──► EnvironmentBible
      │
      ▼
Prompt Intelligence ──► ImagePrompts + VideoPrompts
      (consumes ProductionPlan + Storyboard + ShotPlan + CameraPlan
       + CharacterBible + EnvironmentBible, resolved via shared_core/lookups.py —
       Prompt Intelligence is the one stage that reads nearly everything
       upstream, since a good prompt needs story context, shot action,
       camera treatment, and visual consistency all at once)
      │
      ▼
Voice Script ──► voice_script.txt  (consumes ProductionPlan + Storyboard)
      │
      ▼
Project Manager serializes production-package/ + manifest.json
      │
      ▼
Project Manager sets project state = PACKAGE_READY
```

### Producer Studio (per project)

```
Project Manager loads project (requires state >= PACKAGE_READY)
      │
      ▼
Asset Validation ──► ValidatedAssetManifest (consumes media/ + production-package/manifest.json)
      │
      ▼
Project Manager sets project state = MEDIA_IMPORTED
      │
      ▼
Timeline Planning ──► Timeline
      │
      ▼
Subtitle Planning ──► Subtitles  (consumes voice_script.txt + Timeline)
      │
      ▼
Music Planning ──► MusicPlan
      │
      ▼
Editing Plan ──► EditingPlan  (consumes Timeline + Subtitles + MusicPlan)
      │
      ▼
Thumbnail Prompt ──► thumbnail_prompt.json
      │
      ▼
Publishing Metadata ──► youtube_metadata.json
      │
      ▼
Project Manager sets project state = EDIT_PLAN_READY
      │
      ▼
FFmpeg Export ──► exports/final_video.mp4
      (consumes EditingPlan + media/; paths supplied by Project Manager —
       the one Producer Studio step that performs real media I/O)
      │
      ▼
Project Manager sets project state = VIDEO_RENDERED
      │
      ▼
Human publishes the rendered video externally
      │
      ▼
Project Manager sets project state = PUBLISHED
```

At every arrow, the object crossing it is a typed Pydantic contract, never a raw dict — matching the existing `contract.py` convention.

---

## 12. Agent Responsibilities

### Director Studio

| Agent | Input | Output | Single Responsibility |
|---|---|---|---|
| Research | raw idea / topic | ResearchBrief | Gather supporting context/facts for the idea before story writing begins. |
| Story Planner | ResearchBrief (optional) + raw idea | ProductionPlan | Turn an idea into a structured story: title, logline, characters, scenes. |
| Scene Planner | ProductionPlan | Storyboard | Break each scene into a shot list (what happens, who's present, duration) — no camera detail. |
| Shot Planner | Storyboard | ShotPlan | Confirm/refine per-shot narrative beats independent of camera treatment. |
| Camera Planner | ShotPlan | CameraPlan | Assign camera angle, movement, and coverage per shot. |
| Character Planner | ProductionPlan | CharacterBible | Produce one consistent visual profile per character. |
| Environment Planner | ProductionPlan | EnvironmentBible | Produce one consistent visual profile per unique setting. |
| Prompt Intelligence | ProductionPlan + Storyboard + ShotPlan + CameraPlan + CharacterBible + EnvironmentBible | ImagePrompts, VideoPrompts | Compose final, tool-ready prompts per shot from the full upstream context — story, shot action, camera treatment, and visual consistency, all at once. |
| Voice Script | ProductionPlan + Storyboard | voice_script.txt | Write the full narration/dialogue script. |

Voice Script remains a separate, single-responsibility agent rather than being folded into Prompt Intelligence (§2) — narration writing and shot-prompt writing take different inputs and are governed by different validation rules, even though both end up as text files in the same package.

### Producer Studio

| Agent | Input | Output | Single Responsibility |
|---|---|---|---|
| Asset Validation | media/ + manifest.json | ValidatedAssetManifest | Confirm imported media actually covers what the package expects, in valid formats. |
| Timeline Planning | ValidatedAssetManifest + ShotPlan | Timeline | Sequence validated assets against shot/scene durations. |
| Subtitle Planning | voice_script.txt + Timeline | Subtitles | Time-align narration text to the timeline. |
| Music Planning | Timeline + story mood/tone | MusicPlan | Recommend music cues/sections matching scene mood and pacing. |
| Editing Plan | Timeline + Subtitles + MusicPlan | EditingPlan | Produce the final cut instructions: transitions, layering, timing. |
| Thumbnail Prompt | CharacterBible/EnvironmentBible + story | thumbnail_prompt.json | Write a tool-ready prompt for a thumbnail image. |
| Publishing Metadata | ProductionPlan + EditingPlan | youtube_metadata.json | Write title, description, and tags for publishing. |

Every row in both tables is a single agent, following the standard five-file pattern, with one input contract and one output contract. No agent calls another agent — sequencing is the controller's job (§13), and persistence is Project Manager's job (§4).

---

## 13. Orchestration Flow

- **One controller per studio.** `DirectorStudioController` and `ProducerStudioController` are the only components that know the stage order within their studio. Agents don't know what runs before or after them.
- **Project Manager mediates everything.** Controllers receive typed inputs as arguments from Project Manager and return typed `AgentResult`s to it. They never call `open()`/`write_text()`, never query a store, and never decide file paths.
- **Fail-fast per stage.** If a stage returns `AgentResult(success=False)`, Project Manager stops the run and surfaces the error — it does not attempt to continue with partial/invalid downstream data. This matches the current pipeline's existing fail-fast behavior and is preserved deliberately, not accidentally.
- **Resumable, not idempotent-by-accident.** Project Manager decides which stage is next, based on project state (§8), and invokes only that stage — it does not blindly ask a studio to regenerate everything on every call.
- **Retry policy lives in `BaseAgent`,** inherited by every agent in both studios; controllers do not implement their own retry logic.
- **No cross-studio calls, and no studio ever imports Project Manager.** `DirectorStudioController` never invokes a Producer Studio agent and vice versa. The only thing that crosses the Director → Producer boundary is the Production Package's typed data, mediated entirely by Project Manager.

---

## 14. Coding Standards

- **Five-file agent pattern is mandatory** for every new planner: `agent.py` (orchestration class extending `BaseAgent`), `contract.py` (typed input + public output), `schema.py` (strict LLM output shape), `prompt.py` (prompt string builder), `validator.py` (business-rule checks raising `ContractViolationError`).
- **Two-layer validation is mandatory**: Pydantic schema validation for shape, an explicit `validator.py` function for business rules. An agent with no meaningful business rule still gets a `validator.py` that documents "no additional rules" rather than being skipped.
- **All inter-module data is a typed Pydantic model.** No dicts crossing a function boundary between agent/controller/Project Manager. Any type that ends up in the Production Package or Producer Package is defined once, in `shared_core`'s package schemas (§7) — not redefined ad hoc per agent.
- **No agent imports another agent.** Agents only import from `shared_core`. Sequencing lives in the controller; cross-agent lookups live in `shared_core/lookups.py`.
- **No media-generation API calls inside `director_studio/` or `producer_studio/agents/`,** except FFmpeg export, which is the one explicitly-sanctioned exception and lives in its own isolated `export/` module — never inside an `agents/` package.
- **Director Studio and Producer Studio perform no filesystem I/O.** All persistence — reading project state, writing stage results, writing the Production/Producer Package, updating project state — goes through Project Manager. The sole exception is FFmpeg Export's actual media read/write, which uses paths supplied by Project Manager rather than deciding its own, and which still never touches `project.json`, `manifest.json`, or any other bookkeeping file.
- **Module boundaries are one-directional and I/O is centralized.** `shared_core` depends on nothing else in the project. `project_manager` depends only on `shared_core`, and it imports and invokes `director_studio` and `producer_studio` to run stages. `director_studio` and `producer_studio` depend only on `shared_core` — neither imports `project_manager`, the other studio, or performs any file/database access itself. This makes "no direct filesystem I/O in the studios" a structural guarantee, not just a convention.
- **LLM provider is always injected**, never hardcoded inside an agent — matching the existing `agent = SomeAgent(llm_client)` convention.
- **Errors use the existing exception hierarchy**: `LLMCallError` (the call itself failed), `SchemaValidationError` (shape mismatch), `ContractViolationError` (valid shape, wrong content). New exception types extend this hierarchy rather than introducing parallel ones.
- **Logging** goes through `shared_core/utils/logger.py`'s `get_logger(name)` — no ad hoc `print()` in agent/controller/Project Manager code.
- **Testing**: every `validator.py` has a corresponding unit test file; every controller has at least one integration test exercising the full stage chain with mocked LLM clients; Project Manager has tests covering create/load/save/resume/state-transition behavior, plus package serialization round-trips.
- **Config**: provider-agnostic settings live in `shared_core/config.py`; studio-specific settings live in that studio's own `config.py`; Project Manager has its own `config.py` for storage location and layout, which studios never read directly.

---

## 15. Migration Roadmap

Migration proceeds incrementally. The project remains runnable after every phase; nothing is rewritten from scratch. This roadmap supersedes two earlier framings from the design discussion: a flat, per-run "Production Package writer" (Project Manager now owns package export centrally, not each studio independently), and folding project persistence into Shared Core (Project Manager is now its own layer, per §4).

| # | Phase | Goal | Files affected | Risk |
|---|---|---|---|---|
| 1 | Safety net + cleanup | Add an end-to-end pipeline test (mocked LLMs) before any refactor; remove `test.py` and stub `package-lock.json`. | new `tests/integration/test_pipeline.py`; delete `test.py`, `package-lock.json` | Low |
| 2 | Extract controller | Move `app.py`'s inlined orchestration into a `DirectorStudioController`; `app.py` becomes a thin CLI wrapper. | new `director_studio/controller.py`; `app.py` | Low-Med |
| 3 | Relocate shared lookups | Move `find_environment_for_scene`/`find_characters_for_shot`/`get_unique_settings` into `shared_core/lookups.py`. | new `shared_core/lookups.py`; `agents/*/contract.py` | Low |
| 4 | Introduce Project Manager | Add the Project model, store, and lifecycle state machine as their own module — not inside Shared Core. Controller starts receiving/returning typed data through Project Manager, additively alongside current output; `app.py` updated to call Project Manager instead of the controller directly. | new `project_manager/{project,store,lifecycle}.py`; `director_studio/controller.py`; `app.py` | Medium |
| 5 | Cut over to Project Manager-owned output | Retire flat `outputs/*.json` writes and any studio-side file writes. Production Package schema moves into `shared_core`; `project_manager/package_writer.py` becomes the only thing that serializes `production-package/`. | new `shared_core/production_package_schema.py`, `project_manager/package_writer.py`; `director_studio/controller.py` (I/O removed); `config.py` | Medium (breaking: old flat paths disappear) |
| 6 | Stop auto image generation | Remove the automatic `ImageGenerationAgent` call from the default pipeline; Prompt Intelligence output becomes the package's `image_prompts.json`/`video_prompts.json` directly. Image agent remains available only as an explicit, opt-in manual tool. | `director_studio/controller.py`; `agents/image_generator/*` (untouched, just uninvoked by default) | Medium (visible behavior change) |
| 7 | Add Camera Planner + widen Prompt Intelligence | New agent enriching `ShotPlan` with camera detail, inserted after Shot Planning. Prompt Intelligence updated to consume `ProductionPlan + Storyboard + ShotPlan + CameraPlan + CharacterBible + EnvironmentBible` instead of only the two bibles. | new `agents/camera_planner/*`; `agents/prompt_generator/contract.py`, `prompt.py`; controller | Low-Med |
| 8 | Add Research agent | New optional first stage feeding Story Planner. | new `agents/research/*`; controller | Low |
| 9 | Add Voice Script agent | New agent producing `voice_script.txt`. | new `agents/voice_script/*`; controller, package writer | Low |
| 10 | Split config into shared + overlays | Separate provider-agnostic settings from studio-specific and Project-Manager-specific settings. | `config.py` → `shared_core/config.py` + `director_studio/config.py` + `project_manager/config.py`; import updates across the repo | Medium (wide import surface, mechanical) |
| 11 | Scaffold Producer Studio agents | Build Asset Validation, Timeline, Subtitle, Music, Editing Plan, Thumbnail Prompt, Publishing Metadata agents on the five-file pattern. | new `producer_studio/agents/*`, `producer_studio/controller.py` | Low (zero coupling to Director Studio internals) |
| 12 | FFmpeg Export | Consume the Editing Plan and assemble the final video, using paths supplied by Project Manager. | new `producer_studio/export/ffmpeg_export.py`; `shared_core/producer_package_schema.py`; `project_manager/producer_package_writer.py` | Medium (first external-binary dependency) |

**Sequencing notes:**
- Phases 8 and 9 are mutually independent once Phase 5 lands and can proceed in any order.
- Phase 6 (media-generation compliance) is deliberately placed before new Director Studio agents are added, so the "no auto media" principle is locked in while the surface area is still small.
- Phase 10 is last within Director Studio work because it has the widest import surface — cheapest once Phases 6–9 are no longer moving targets.
- Milestone G (Phases 11–12) has no code dependency on Director Studio internals beyond "reads a completed Project" and can start in parallel with Director Studio work if resourcing allows.

### Active Technical Debt Ledger

Every item below was explicitly accepted at the milestone that introduced it, not discovered later. This table is the migration checklist for paying each one off — an item is only removed from this ledger once its "Planned Removal Milestone" has actually landed, not before.

| # | Item | Reason | Temporary Owner | Planned Removal Milestone |
|---|---|---|---|---|
| 1 | `shared_core/lookups.py` imports types from `agents/*` (`CharacterSheet`, `EnvironmentSheet`, `ProductionPlan`, etc.), violating §7's "Shared Core depends on nothing else." | The cross-agent lookup functions were relocated to Shared Core (Phase 3) before their underlying types existed there — Shared Core has no types of its own yet to depend on instead. | `shared_core/lookups.py` (inline `TODO(Phase 5)` comment) | **Phase 5** — once Production Package schema types move into Shared Core, `lookups.py`'s imports reverse to depend on Shared Core's own types instead of `agents/*`. |
| 2 | `voice_script.txt` is a placeholder stub, not real narration content. | No Voice Script agent exists yet to generate real content; the file exists so the Production Package's shape is stable ahead of that agent's introduction. | `project_manager/package_writer.py` (`manifest.json` marks its status `"pending"`) | **Phase 9** — Add Voice Script agent. |
| 3 | `ProjectState` implements 7 states, not ARCHITECTURE.md §8's full 14 (`RESEARCHED`, `SHOTS_COMPLETE`, `CAMERA_COMPLETE` are absent). | No Research or Camera Planner agent exists yet, and Scene Planner still produces shot-level detail as part of `SCENES_COMPLETE`. | `project_manager/project.py` (`ProjectState` enum, with an inline comment noting the gap) | `CAMERA_COMPLETE` → **Phase 7**. `RESEARCHED` → **Phase 8**. `SHOTS_COMPLETE` has **no assigned phase yet** — the roadmap currently has no distinct Shot Planner phase, so this needs an explicit decision (add one, or drop the state from the target design) before it can be scheduled. |
| 4 | The Production Package's shape is defined as builder functions in `project_manager/package_writer.py`, not as formal typed schemas in Shared Core. | The Project Manager milestone moved *where* the package is written, not *what a package is* as a first-class Shared Core type — that formalization is Phase 5's specific job. | `project_manager/package_writer.py` | **Phase 5** — Production Package schema formally extracted into `shared_core/production_package_schema.py`. |
| 5 | `ProjectManager.get_images_dir()` returns a flat, non-project-scoped legacy path (`outputs/images/`), and `ImageGenerationAgent` still writes image bytes directly instead of the pipeline only ever producing prompts. | Automatic image generation is legacy CLI behavior predating this migration; refactoring `ImageGenerationAgent` was explicitly out of scope for the Project Manager milestone. | `project_manager/manager.py` (`get_images_dir`) + `agents/image_generator/agent.py` (unchanged) | **Phase 6** — Stop auto image generation; `ImageGenerationAgent` becomes an explicit, opt-in manual tool, no longer wired into the default pipeline. |

---

## 16. Future Expansion Plan

Ideas explicitly out of scope for the migration above, but consistent with this architecture and worth designing toward:

- **Web UI for Director Studio**, replacing/augmenting the CLI — talks to Project Manager exactly as the CLI does today, since orchestration was already decoupled from `app.py` in Phase 2 and mediated through Project Manager from Phase 4 onward.
- **Style preset library** — reusable art-style/tone bundles that Character Planner, Environment Planner, and Prompt Intelligence can all reference, reducing repeated `art_style` string plumbing.
- **Per-tool prompt formatting** — a thin adapter layer in Prompt Intelligence that renders the same underlying prompt data into Midjourney-, Flux-, or Veo-specific syntax, instead of one generic string.
- **Project versioning/diffing** — since Projects already record which upstream inputs each stage was generated from (§8), a diff view between two versions of a re-run stage becomes possible without new storage design.
- **Multi-format export from Producer Studio** — Editing Plan output as an EDL/Premiere XML target in addition to direct FFmpeg export, for users who want to finish in a traditional NLE.
- **Batch project generation** — running Director Studio across many ideas unattended (e.g. a content calendar), relying on the same resumable, Project-Manager-driven controller.
- **Collaborative projects** — multiple humans attached to one project (one doing story review, another doing asset generation), enabled by Project Manager already being the single writer of project state and owner of all persistence.
- **Plugin system for new agents** — since every agent is a self-contained five-file package with no cross-agent imports, third-party or experimental agents (e.g. a "Trailer Cut Planner") can be added to either studio's `agents/` directory without touching existing ones.

---

*This document is the frozen architecture. Deviations discovered during implementation should be raised as a proposed amendment to this document before being coded, not worked around silently.*

---

## Architecture Status

**Status:** FROZEN

**Version:** 1.0.0

**Last Updated:** 2026-07-21

Breaking changes require:
- Architecture review
- ADR (Architecture Decision Record)
- Migration plan

Minor implementation changes do not require architecture updates.
