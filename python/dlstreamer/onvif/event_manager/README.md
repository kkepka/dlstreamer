# dlstreamer.onvif.event_manager

Library for discovering ONVIF cameras that expose the Events service.

This module focuses on event capability detection and event data models.

## Public API

The public API is defined in api.py and re-exported by __init__.py.

### Data model

| Type | Description |
|---|---|
| EventNotification | Parsed ONVIF NotificationMessage (topic, source, data, timestamp, operation). |
| EventFilter | Topic-expression filter descriptor used for PullPoint subscription requests. |
| EventCapableCamera | Camera descriptor confirmed to expose ONVIF Events service. |

### Functions

| Function | Signature | Input arguments | Return values | Description |
|---|---|---|---|---|
| is_event_capable | is_event_capable(hostname: str, port: int, username: str = "", password: str = "", verbose: bool = False) -> bool | hostname, port, username, password, verbose | bool | Quick probe that returns True if camera responds to Events GetServiceCapabilities. |
| find_event_capable_cameras | find_event_capable_cameras(cameras: Iterable[dict], username: str = "", password: str = "", verbose: bool = False) -> Iterator[EventCapableCamera] | cameras (iterable of descriptors), username, password, verbose | Iterator[EventCapableCamera] | Reads camera descriptors and yields only event-capable cameras (sync). |
| find_event_capable_cameras_async | find_event_capable_cameras_async(cameras: Iterable[dict] \| AsyncIterable[dict], username: str = "", password: str = "", verbose: bool = False) -> AsyncIterator[EventCapableCamera] | cameras (sync or async source), username, password, verbose | AsyncIterator[EventCapableCamera] | Async variant that accepts both sync and async camera sources. |
| pull_events_once | pull_events_once(hostname: str, port: int, username: str = "", password: str = "", verbose: bool = False, timeout: str = "PT30S", limit: int = 100, termination_time: str = "PT1H", topic_filter: EventFilter \| None = None) -> list[EventNotification] | hostname, port, credentials, timeout, limit, termination_time, topic_filter | list[EventNotification] | Simplest sync call: subscribe, pull one batch, and close automatically. |
| stream_events | stream_events(hostname: str, port: int, username: str = "", password: str = "", verbose: bool = False, timeout: str = "PT30S", limit: int = 100, termination_time: str = "PT1H", topic_filter: EventFilter \| None = None, renew_every: float \| None = 300.0) -> AsyncIterator[EventNotification] | hostname, port, credentials, pull settings, optional filter, renew_every | AsyncIterator[EventNotification] | Simplest async stream with automatic subscribe/renew/close lifecycle. |

## Usage examples

### 1) Find event-capable cameras (sync)

```python
from dlstreamer.onvif.discovery import discover_onvif_cameras
from dlstreamer.onvif.event_manager import find_event_capable_cameras

for cap in find_event_capable_cameras(
    discover_onvif_cameras(),
    username="admin",
    password="secret",
):
    print(cap.camera_id)
```

### 2) Find event-capable cameras (async)

```python
import asyncio
from dlstreamer.onvif.discovery import discover_onvif_cameras_async
from dlstreamer.onvif.event_manager import find_event_capable_cameras_async

async def main():
    async for cap in find_event_capable_cameras_async(
        discover_onvif_cameras_async(),
        username="admin",
        password="secret",
    ):
        print(cap.camera_id)

asyncio.run(main())
```

### 3) Pull one batch of events (sync)

```python
from dlstreamer.onvif.event_manager import pull_events_once

notes = pull_events_once(
    hostname="10.0.0.15",
    port=80,
    username="admin",
    password="secret",
    timeout="PT5S",
    limit=20,
)

for note in notes:
    print(note.short())
```

### 4) Stream events continuously (async)

```python
import asyncio
from dlstreamer.onvif.event_manager import stream_events

async def main():
    async for note in stream_events(
        hostname="10.0.0.15",
        port=80,
        username="admin",
        password="secret",
        timeout="PT10S",
        limit=50,
    ):
        print(note.short())

asyncio.run(main())
```

## Advanced engine (non-public API)

For full PullPoint lifecycle control (subscribe, pull, renew, unsubscribe, stream),
use the engine module directly:

```python
from dlstreamer.onvif.event_manager.engine import OnvifEventEngine
```

Use the engine only when you need manual lifecycle control
(explicit subscribe / renew / unsubscribe steps).

## Data contracts

Input camera descriptor format:

```python
{"hostname": "10.0.0.15", "port": 80}
```

Event-capable camera format:

```python
{
    "hostname": "10.0.0.15",
    "port": 80,
    "error": None,
    "camera_id": "10.0.0.15:80",
    "ok": True,
}
```

## Notes

- Capability detection uses ONVIF Events GetServiceCapabilities.
- Public API is intentionally simple (functions + dataclasses).
- For camera discovery, use dlstreamer.onvif.discovery.
