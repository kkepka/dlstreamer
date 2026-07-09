# dlstreamer.onvif.discovery

Library for discovering ONVIF cameras in the local network using WS-Discovery (SOAP over UDP multicast).

This module is responsible only for discovery (finding host/port). Profile reading and RTSP URL retrieval are in:
- `dlstreamer.onvif.camera_profiles`

## Public API

The public API is defined in `api.py` and re-exported by `__init__.py`.

### Functions

| Function | Signature | Input arguments | Return values | Description |
|---|---|---|---|---|
| discover_onvif_cameras | discover_onvif_cameras(verbose: bool = False) -> Iterator[dict] | verbose: bool = False | Iterator[dict], where each item has the form **{"hostname": str, "port": int}** | Synchronous generator that streams discovered cameras. |
| discover_onvif_cameras_async | discover_onvif_cameras_async(verbose: bool = False) -> AsyncIterator[dict] | verbose: bool = False | AsyncIterator[dict], where each item has the form **{"hostname": str, "port": int}** | Asynchronous generator (`async for`) that streams discovered cameras. |
| extract_xaddrs | extract_xaddrs(xml_string: str) -> Optional[str] | xml_string: str | Optional[str] (the XAddrs value or None) | XML helper that reads the XAddrs field from a ProbeMatch response. |
| parse_xaddrs_url | parse_xaddrs_url(xaddrs: str) -> dict | xaddrs: str | dict with keys: full_url, scheme, hostname, port, path, base_url | Parses the first URL from XAddrs and returns its components. |

## Usage examples

### 1) Synchronous function

```python
from dlstreamer.onvif.discovery import discover_onvif_cameras

for camera in discover_onvif_cameras(verbose=True):
    print(camera["hostname"], camera["port"])
```

### 2) Asynchronous function

```python
import asyncio
from dlstreamer.onvif.discovery import discover_onvif_cameras_async

async def main():
    async for camera in discover_onvif_cameras_async(verbose=False):
        print(camera)

asyncio.run(main())
```

## Data contract

Each discovery result has the form **{"hostname": str, "port": int}**.

## Notes

- Results are returned as a stream (camera by camera).
- The discovery module does not connect to ONVIF Media Service and does not read profiles.
- For profiles/RTSP, use `dlstreamer.onvif.camera_profiles`.
