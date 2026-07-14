# `video_engine` library — overview

The `video_engine` library orchestrates the full lifecycle: **ONVIF camera
discovery → matching against configuration → launching DL Streamer pipelines →
dynamic, event-driven changes**.

## Layered architecture

```mermaid
flowchart TD
    subgraph Internal["<b><big>Video Engine</big></b>"]
        direction TB
        API["Public API<br/><b>__init__.py + api.py</b><br/>(facade + module-level functions)"]
        subgraph Core["Core layer"]
            ENGINE["<b>engine.py</b><br/>VideoEngine"]
            DYNAMIC["<b>dynamic.py</b><br/>DynamicPipelineController"]
        end
        subgraph Data["Data layer"]
            MODEL["<b>model.py</b><br/>dataclasses"]
        end
    end
    subgraph External["External (ONVIF dependencies)"]
        direction TB
        DISC["discovery"]
        PROF["camera_profiles"]
        EVT["event_manager"]
        PTZ["ptz"]
    end

    API --> ENGINE
    API --> DYNAMIC
    API --> MODEL
    API -.re-export.-> PROF & PTZ & EVT
    ENGINE --> MODEL
    ENGINE --> DISC
    ENGINE --> PROF
    DYNAMIC --> ENGINE
    DYNAMIC --> MODEL
    DYNAMIC --> EVT
    MODEL ~~~ External
    style Internal fill:#e8f0fe,stroke:#4285f4,stroke-width:2px
    style External fill:#f1f3f4,stroke:#9aa0a6,stroke-width:2px
```

### Diagram legend

```mermaid
flowchart LR
    u1((" ")) -->|"solid: uses / calls (internal dependency)"| u2((" "))
    d1((" ")) -.->|"dashed: data flow / re-export (across libraries)"| d2((" "))
```

- **Solid arrow** `-->`: an internal dependency — one module uses, calls or contains another.
- **Dashed arrow** `-.->`: a looser data flow between libraries (e.g. camera descriptors) or a re-export of another library's public API.
- Edge labels (e.g. `re-export`, `Probe / ProbeMatch`, `{hostname, port}`) name the concrete payload or operation.

---

## 1. `__init__.py` — package shim

A minimal file that re-exports everything from `api.py`. This lets users write
`from dlstreamer.onvif.video_engine import ...` instead of reaching into `api`.
It follows the repository convention (public API in `api.py`, re-exported via
`__init__.py`).

---

## 2. `model.py` — data models (pure dataclasses)

All objects are `@dataclass`, most of them `frozen=True` (immutable). They carry
no business logic — only data and light normalization.

| Class | Role |
|-------|------|
| `CameraIdentity` | Normalized camera key (`hostname:port:MAC`). MAC normalized to uppercase with `:` |
| `PipelineBinding` | Association of a pipeline with a camera (+ `binding_id`, events, profile, optional `username`/`password` for RTSP-URL resolution) |
| `CameraRuntimeState` | Live camera state (`discovered`/`matched`, `last_seen`, assigned bindings) |
| `VideoEngineEvent` | Callback payload emitted by the engine |
| `CameraEventDefinition` | ONVIF event definition attached to a camera |
| `PipelineAction` | Enum: `ADD`, `MODIFY`, `REMOVE`, `RESTART` |
| `EventTrigger` | Notification-matching condition (logical AND of fields) |
| `EventRule` | Binds an `EventTrigger` → `PipelineAction` on a specific binding |

Helper functions: `as_camera_identity()` (builds an identity from a dict/object)
and `pipeline_list()` (normalizes a pipeline given as a string/list).

```mermaid
classDiagram
    class CameraIdentity {
        hostname: str
        port: int
        mac: str
        key() str
    }
    class PipelineBinding {
        camera: CameraIdentity
        pipeline: str|Sequence
        binding_id: str
        events: tuple
        profile_name: str
        username: str
        password: str
        to_dict()
    }
    class EventRule {
        name: str
        camera: CameraIdentity
        trigger: EventTrigger
        action: PipelineAction
        target_binding_id: str
        pipeline
    }
    class EventTrigger {
        topic_contains
        property_operation
        data_equals: dict
    }
    class PipelineAction {
        <<enum>>
        ADD / MODIFY / REMOVE / RESTART
    }
    PipelineBinding --> CameraIdentity
    EventRule --> CameraIdentity
    EventRule --> EventTrigger
    EventRule --> PipelineAction
    CameraRuntimeState --> CameraIdentity
    CameraEventDefinition --> CameraIdentity
```

---

## 3. `api.py` — public facade

It creates a **single shared singleton** `_DEFAULT_ENGINE = VideoEngine()` and
exposes module-level functions that delegate to it (procedural style). It also
re-exports the entire `camera_profiles`, `ptz`, and `event_manager` libraries.

API groups:
- **Factory / lifecycle**: `create_video_engine`, `get_video_engine`, `start_video_engine`, `stop_video_engine`, `destroy_video_engine`
- **Discovery**: `discovery_start/stop`
- **Configuration**: `setTimeout/getTimeout`, `setDiscoveryTime/getDiscoveryTime`, `load_config`, `save_config`
- **Pipeline management**: `list_camera_pipeline_pairs`, `get_pipeline_for_camera`, `set_camera_pipeline`
- **Events**: `set_camera_event`, `list_camera_events`
- **Callbacks**: `register_callback`, `unregister_callback`
- **State**: `get_active_cameras`, `get_active_pipelines`
- **Dynamic control**: `create_dynamic_controller`

---

## 4. `engine.py` — `VideoEngine` (runtime core)

At the heart is a thread-safe class (protected by `threading.RLock`) with two
background threads:

- **Discovery thread** (`_discovery_loop`) — periodically discovers ONVIF
  cameras, matches them to bindings, and starts pipelines.
- **Reaper thread** (`_reaper_loop`) — removes "stale" cameras (no `last_seen`
  within `timeout`) and stops their pipelines.

Pipelines are launched as processes (`subprocess.Popen`), logging to
`/tmp/video_engine_pipeline_*.log`. It supports the `{rtsp_url}` placeholder,
resolved from the camera profile (`camera_profiles.read_camera_profiles`) using
the binding's `username`/`password` (or the engine defaults set with
`set_default_credentials`).

### Flow chart — discovery and reaper loops

```mermaid
flowchart TD
    START([start]) --> DS["discovery_start()<br/>launch discovery thread"]
    START --> RS["_start_reaper()<br/>launch reaper thread"]

    DS --> LOOP{stop_event?}
    LOOP -- no --> DISC["discover_onvif_cameras()"]
    DISC --> SEEN["_handle_camera_seen()"]
    SEEN --> MATCH{"binding matches?"}
    MATCH -- yes --> STATE["state = 'matched'<br/>touch(last_seen)"]
    MATCH -- no --> STATE2["state = 'discovered'"]
    STATE --> SPAWN["_start_pipeline_if_needed()<br/>spawn subprocess"]
    SPAWN --> EMIT["_emit('pipeline_started')"]
    STATE2 --> WAIT["wait(discovery_time)"]
    EMIT --> WAIT
    WAIT --> LOOP
    LOOP -- yes --> ENDD([end])

    RS --> RLOOP{stop_event?}
    RLOOP -- no --> REAP["_reap_stale_cameras()"]
    REAP --> CHECK{"now - last_seen<br/>> timeout?"}
    CHECK -- yes --> LOST["_handle_camera_lost()<br/>stop pipeline + emit 'camera_lost'"]
    CHECK -- no --> RWAIT["wait(min timeout,discovery)"]
    LOST --> RWAIT
    RWAIT --> RLOOP
    RLOOP -- yes --> RENDD([end])
```

### Sequence chart — camera discovery and pipeline start

```mermaid
sequenceDiagram
    participant App as Application
    participant API as api.py
    participant Eng as VideoEngine
    participant DThr as Discovery thread
    participant Disc as discovery
    participant Prof as camera_profiles
    participant Proc as subprocess

    App->>API: set_camera_pipeline(host, port, pipeline)
    API->>Eng: set_camera_pipeline(...)
    Eng->>Eng: add PipelineBinding
    App->>API: start_video_engine()
    API->>Eng: start()
    Eng->>DThr: launch discovery thread

    loop every discovery_time
        DThr->>Disc: discover_onvif_cameras()
        Disc-->>DThr: [cameras]
        DThr->>Eng: _handle_camera_seen(camera)
        Eng->>Eng: match bindings, set state 'matched'
        Eng->>Eng: _start_pipeline_if_needed(binding)
        alt pipeline contains {rtsp_url}
            Eng->>Prof: read_camera_profiles()
            Prof-->>Eng: rtsp_url
            Eng->>Eng: substitute {rtsp_url}
        end
        Eng->>Proc: Popen(command) → log /tmp
        Eng->>App: callback VideoEngineEvent('pipeline_started')
    end
```

Pipeline mutation methods (also used by the dynamic layer): `add_pipeline`
(idempotent), `remove_pipeline`, `replace_pipeline` (stop→swap→start), and
`restart_pipeline`.

---

## 5. `dynamic.py` — event-driven dynamic control

Implements a **restart-based strategy (Option A)**: "modifying" a pipeline means
stopping the process and spawning a new one. Responsibilities are split across 5
small classes (single responsibility):

| Class | Responsibility |
|-------|----------------|
| `EventRuleParser` | Deserialize rules from dict/JSON → `EventRule`; resolves `pipeline_ref` against the pipeline library |
| `EventRuleMatcher` | Pure (stateless) matching of a notification against a trigger |
| `PipelineActionExecutor` | Map `PipelineAction` → `VideoEngine` call |
| `CameraEventWorker` | Thread pulling ONVIF events for a **single** camera |
| `DynamicPipelineController` | Orchestration: groups rules per camera, runs workers, dispatch |

### Configuration files (two-file model)

Pipeline definitions and the camera/event bindings live in **separate** files so a
pipeline is defined once and referenced by id:

- **Pipeline library** (`video_engine_pipelines.json`) — a mapping of
  `id → pipeline` (command list or string). **No camera information.**
  Loaded with `DynamicPipelineController.load_pipeline_library(path)`.

  ```json
  { "pipelines": {
      "move_detected_ball_test": [
        "gst-launch-1.0", "-v", "videotestsrc", "pattern=ball", "!",
        "videoconvert", "!", "gvawatermark",
        "displ-cfg=ff-custom-txt='Move detected'", "!",
        "videoconvert", "!", "autovideosink"
      ]
  } }
  ```

- **Rules** (`video_engine_rules.json`) — cameras + triggers + a `pipeline_ref`
  pointing at a pipeline in the library (an inline `pipeline` is still accepted).
  Loaded with `DynamicPipelineController.load_rules(path)` after the library.

  ```json
  {
    "name": "run-ball-test-on-motion",
    "camera": { "hostname": "10.91.106.65", "port": 2020 },
    "trigger": { "data_equals": { "IsMotion": "true" } },
    "action": "add",
    "target_binding_id": "move_detected_ball_test",
    "pipeline_ref": "move_detected_ball_test",
    "username": "admin", "password": "r00tme"
  }
  ```

**Credentials**: each rule/binding may carry its own `username`/`password` (used
for event subscription and `{rtsp_url}` resolution). When omitted, the engine and
controller fall back to defaults set via `set_default_credentials(user, pass)`.

### Flow chart — rule dispatch

```mermaid
flowchart TD
    N([EventNotification]) --> DISP["_dispatch(camera, notification)"]
    DISP --> FILT["rules for this camera"]
    FILT --> M{"matcher.matches()?<br/>topic + property_op + data_equals"}
    M -- no --> SKIP[skip]
    M -- yes --> EXEC["executor.execute(rule)"]
    EXEC --> ACT{action}
    ACT -- ADD --> ADD["engine.add_pipeline()"]
    ACT -- MODIFY --> MOD["engine.replace_pipeline()"]
    ACT -- REMOVE --> REM["engine.remove_pipeline()"]
    ACT -- RESTART --> RST["engine.restart_pipeline()"]
```

### Sequence chart — from ONVIF event to pipeline change

```mermaid
sequenceDiagram
    participant App as Application
    participant Ctrl as DynamicPipelineController
    participant Wrk as CameraEventWorker
    participant Onvif as OnvifEventEngine
    participant Mtch as EventRuleMatcher
    participant Exec as PipelineActionExecutor
    participant Eng as VideoEngine

    App->>Ctrl: load_rules(rules.json)
    Ctrl->>Ctrl: parser.parse_rules()
    App->>Ctrl: start()
    Ctrl->>Wrk: 1 worker per camera (start)

    loop pull loop
        Wrk->>Onvif: subscribe() + pull(timeout)
        Onvif-->>Wrk: [EventNotification]
        Wrk->>Ctrl: _dispatch(camera, notification)
        Ctrl->>Mtch: matches(rule, notification)
        Mtch-->>Ctrl: True/False
        alt matched
            Ctrl->>Exec: execute(rule)
            Exec->>Eng: add/replace/remove/restart_pipeline()
            Eng->>Eng: stop proc → spawn new proc
        end
        Wrk->>Onvif: renew() every renew_every
    end

    App->>Ctrl: stop()
    Ctrl->>Wrk: stop_event.set() + join
```

---

## Data-flow summary

```mermaid
flowchart LR
    subgraph Discovery["Discovery path (proactive)"]
        direction TB
        D1["ONVIF camera appears"] --> D2["match to PipelineBinding"] --> D3["start pipeline"]
    end
    subgraph Events["Event path (reactive)"]
        direction TB
        E1["ONVIF event"] --> E2["EventRule match"] --> E3["ADD/MODIFY/REMOVE/RESTART"]
    end
    Discovery --> ENGINE["VideoEngine<br/>manages processes"]
    Events --> ENGINE
    ENGINE --> CB["VideoEngineEvent callbacks"]
```

**Key idea:** `VideoEngine` is the execution layer (processes, threads, state),
while `DynamicPipelineController` is a rule layer on top of it. Both share the
models from `model.py`, and `api.py` ties everything together into a simple,
functional public interface.
