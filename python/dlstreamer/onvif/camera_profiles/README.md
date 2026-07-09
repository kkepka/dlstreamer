# dlstreamer.onvif.camera_profiles

Library for reading ONVIF media profiles from cameras discovered on the local network.

This module consumes camera descriptors produced by discovery and returns media profiles (video/audio/PTZ/RTSP) per camera.

## Public API

The public API is defined in api.py and re-exported by __init__.py.

### Data model

| Type | Description |
|---|---|
| ONVIFProfile | Media profile object with video/audio/PTZ fields and RTSP URL. |
| CameraProfilesResult | Per-camera result wrapper: hostname, port, profiles, error, ok. |

### Functions

| Function | Signature | Input arguments | Return values | Description |
|---|---|---|---|---|
| read_camera_profiles | read_camera_profiles(**cameras: Iterable[dict], username: str = "", password: str = ""**, verbose: bool = False) -> Iterator[CameraProfilesResult] | cameras (iterable of camera descriptors), username, password, verbose | Iterator[CameraProfilesResult] | Reads profiles from a synchronous camera source and yields one result per camera. |
| read_camera_profiles_async | read_camera_profiles_async(**cameras: Iterable[dict] \| AsyncIterable[dict], username: str = "", password: str = ""**, verbose: bool = False) -> AsyncIterator[CameraProfilesResult] | cameras (sync or async camera source), username, password, verbose | AsyncIterator[CameraProfilesResult] | Async variant that works with both sync and async camera sources. |

## Usage examples

### 1) Read profiles from synchronous discovery

```python
from dlstreamer.onvif.discovery import discover_onvif_cameras
from dlstreamer.onvif.camera_profiles import read_camera_profiles

for result in read_camera_profiles(
    discover_onvif_cameras(),
    username="admin",
    password="secret",
):
    if result.ok:
        for profile in result.profiles:
            print(result.hostname, profile.name, profile.rtsp_url)
    else:
        print(result.hostname, result.error)
```

### 2) Read profiles from asynchronous discovery

```python
import asyncio
from dlstreamer.onvif.discovery import discover_onvif_cameras_async
from dlstreamer.onvif.camera_profiles import read_camera_profiles_async

async def main():
    async for result in read_camera_profiles_async(
        discover_onvif_cameras_async(),
        username="admin",
        password="secret",
    ):
        print(result.hostname, result.ok, len(result.profiles))

asyncio.run(main())
```

## Return value examples

### read_camera_profiles / read_camera_profiles_async

Successful per-camera item:

```python
CameraProfilesResult(
    hostname="10.0.0.15",
    port=80,
    profiles=[
        ONVIFProfile(
            name="Profile_1",
            token="ProfileToken_1",
            vec_encoding="H264",
            vec_resolution={"width": 1920, "height": 1080},
            rtsp_url="rtsp://10.0.0.15:554/stream1",
            ptz_token="PTZConfigToken_1",
        )
    ],
    error=None,
)
```

Failure per-camera item:

```python
CameraProfilesResult(
    hostname="10.0.0.99",
    port=80,
    profiles=[],
    error="TimeoutError: timed out",
)
```

## Data contracts

Input camera descriptor format:

```python
{"hostname": "10.0.0.15", "port": 80}
```

Per-camera result format:

```python
{
    "hostname": "10.0.0.15",
    "port": 80,
    "profiles": [ONVIFProfile, ...],
    "error": None,
    "ok": True,
}
```

## Notes

- One result is yielded per camera, so errors on one camera do not stop the whole sweep.
- This module performs ONVIF Media service calls and may require valid camera credentials.
- For camera discovery itself, use dlstreamer.onvif.discovery.
