# ==============================================================================
# Copyright (C) 2026 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================
"""Data models for :mod:`dlstreamer.onvif.video_engine`."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence, Tuple


def _normalize_mac(mac: Optional[str]) -> Optional[str]:
    if mac is None:
        return None
    normalized = mac.strip().upper().replace("-", ":")
    return normalized or None


@dataclass(frozen=True)
class CameraIdentity:
    """Normalized camera key used for matching and state tracking."""

    hostname: str
    port: int
    mac: Optional[str] = None

    def key(self) -> str:
        normalized_mac = _normalize_mac(self.mac)
        if normalized_mac:
            return f"{self.hostname}:{self.port}:{normalized_mac}"
        return f"{self.hostname}:{self.port}"


@dataclass(frozen=True)
class PipelineBinding:
    """A configured pipeline associated with a camera identity."""

    camera: CameraIdentity
    pipeline: Sequence[str] | str
    binding_id: str
    events: Tuple[str, ...] = field(default_factory=tuple)
    profile_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "camera": {
                "hostname": self.camera.hostname,
                "port": self.camera.port,
                "mac": self.camera.mac,
            },
            "binding_id": self.binding_id,
            "pipeline": list(self.pipeline) if not isinstance(self.pipeline, str) else self.pipeline,
            "events": list(self.events),
        }


@dataclass
class CameraRuntimeState:
    """Live state for a discovered camera."""

    camera: CameraIdentity
    status: str = "discovered"
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    pipeline_binding_ids: Tuple[str, ...] = field(default_factory=tuple)
    error: Optional[str] = None

    def touch(self) -> None:
        self.last_seen = datetime.now(timezone.utc)


@dataclass(frozen=True)
class VideoEngineEvent:
    """Callback payload emitted by the engine."""

    kind: str
    camera: CameraIdentity
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class CameraEventDefinition:
    """ONVIF event definition attached to a camera."""

    name: str
    camera: CameraIdentity
    topic_filter: Optional[str] = None
    renew_every: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def as_camera_identity(camera: Any) -> CameraIdentity:
    """Build a :class:`CameraIdentity` from a dict-like camera descriptor."""

    if isinstance(camera, CameraIdentity):
        return camera

    if not isinstance(camera, dict):
        raise TypeError("camera must be a mapping with hostname and port")

    hostname = camera.get("hostname") or camera.get("ip")
    port = camera.get("port")
    mac = camera.get("mac") or camera.get("mac_address")

    if not hostname or port is None:
        raise ValueError("camera descriptor requires hostname/ip and port")

    return CameraIdentity(str(hostname), int(port), _normalize_mac(mac))


def pipeline_list(value: Sequence[str] | str) -> Sequence[str] | str:
    """Return the pipeline as stored, after trivial normalization."""

    if isinstance(value, str):
        return value.strip()
    return tuple(str(item) for item in value)
