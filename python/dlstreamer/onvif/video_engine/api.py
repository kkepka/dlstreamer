# ==============================================================================
# Copyright (C) 2026 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================
"""Public API for :mod:`dlstreamer.onvif.video_engine`."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from .engine import VideoEngine
from .model import (
    CameraEventDefinition,
    CameraIdentity,
    CameraRuntimeState,
    PipelineBinding,
    VideoEngineEvent,
)
from ..camera_profiles import (
    ONVIFProfile,
    CameraProfilesResult,
    read_camera_profiles,
    read_camera_profiles_async,
)
from ..ptz import (
    PTZVector,
    PTZStatus,
    PTZPreset,
    PTZCapableProfile,
    is_ptz_profile,
    find_ptz_capable_profiles,
    find_ptz_capable_profiles_async,
    PTZController,
)
from ..event_manager import (
    EventCapableCamera,
    EventFilter,
    EventNotification,
    is_event_capable,
    find_event_capable_cameras,
    find_event_capable_cameras_async,
    pull_events_once,
    stream_events,
)

_DEFAULT_ENGINE = VideoEngine()


def create_video_engine(
    config_path: str | Path | None = None,
    *,
    discovery_time: int = 60,
    timeout: int = 120,
    verbose: bool = False,
) -> VideoEngine:
    return VideoEngine(
        config_path=config_path,
        discovery_time=discovery_time,
        timeout=timeout,
        verbose=verbose,
    )


def get_video_engine() -> VideoEngine:
    return _DEFAULT_ENGINE


def start_video_engine() -> None:
    _DEFAULT_ENGINE.start()


def stop_video_engine() -> None:
    _DEFAULT_ENGINE.stop()


def destroy_video_engine() -> None:
    _DEFAULT_ENGINE.destroy()


def discovery_start() -> None:
    _DEFAULT_ENGINE.discovery_start()


def discovery_stop() -> None:
    _DEFAULT_ENGINE.discovery_stop()


def setTimeout(sec: int) -> None:
    _DEFAULT_ENGINE.setTimeout(sec)


def getTimeout() -> int:
    return _DEFAULT_ENGINE.getTimeout()


def setDiscoveryTime(sec: int) -> None:
    _DEFAULT_ENGINE.setDiscoveryTime(sec)


def getDiscoveryTime() -> int:
    return _DEFAULT_ENGINE.getDiscoveryTime()


def load_config(config_path: str | Path) -> None:
    _DEFAULT_ENGINE.load_config(config_path)


def save_config() -> None:
    _DEFAULT_ENGINE.save_config()


def list_camera_pipeline_pairs() -> list[dict[str, Any]]:
    return _DEFAULT_ENGINE.list_camera_pipeline_pairs()


def get_pipeline_for_camera(hostname: str, port: int, mac: str | None = None) -> list[dict[str, Any]]:
    return _DEFAULT_ENGINE.get_pipeline_for_camera(hostname, port, mac)


def set_camera_pipeline(
    hostname: str,
    port: int,
    pipeline: Sequence[str] | str,
    *,
    mac: str | None = None,
    binding_id: str | None = None,
    events: Iterable[str] | None = None,
    persist: bool = False,
) -> PipelineBinding:
    return _DEFAULT_ENGINE.set_camera_pipeline(
        hostname,
        port,
        pipeline,
        mac=mac,
        binding_id=binding_id,
        events=events,
        persist=persist,
    )


def set_camera_event(
    hostname: str,
    port: int,
    event_name: str,
    *,
    mac: str | None = None,
    topic_filter: str | None = None,
    renew_every: float | None = None,
    **metadata: Any,
) -> CameraEventDefinition:
    return _DEFAULT_ENGINE.set_camera_event(
        hostname,
        port,
        event_name,
        mac=mac,
        topic_filter=topic_filter,
        renew_every=renew_every,
        **metadata,
    )


def list_camera_events(hostname: str, port: int, mac: str | None = None) -> list[dict[str, Any]]:
    return _DEFAULT_ENGINE.list_camera_events(hostname, port, mac)


def register_callback(callback: Callable[[VideoEngineEvent], None]) -> None:
    _DEFAULT_ENGINE.register_callback(callback)


def unregister_callback(callback: Callable[[VideoEngineEvent], None]) -> None:
    _DEFAULT_ENGINE.unregister_callback(callback)


def get_active_cameras() -> list[dict[str, Any]]:
    return _DEFAULT_ENGINE.get_active_cameras()


def get_active_pipelines() -> list[dict[str, Any]]:
    return _DEFAULT_ENGINE.get_active_pipelines()


__all__ = [
    # ===== Model classes =====
    "CameraEventDefinition",
    "CameraIdentity",
    "CameraRuntimeState",
    "PipelineBinding",
    "VideoEngine",
    "VideoEngineEvent",
    
    # ===== Factory and lifecycle =====
    "create_video_engine",
    "get_video_engine",
    "start_video_engine",
    "stop_video_engine",
    "destroy_video_engine",
    
    # ===== Discovery =====
    "discovery_start",
    "discovery_stop",
    
    # ===== Configuration =====
    "setTimeout",
    "getTimeout",
    "setDiscoveryTime",
    "getDiscoveryTime",
    "load_config",
    "save_config",
    
    # ===== Camera pipeline management =====
    "list_camera_pipeline_pairs",
    "get_pipeline_for_camera",
    "set_camera_pipeline",
    
    # ===== Camera events =====
    "set_camera_event",
    "list_camera_events",
    
    # ===== Callbacks =====
    "register_callback",
    "unregister_callback",
    
    # ===== State query =====
    "get_active_cameras",
    "get_active_pipelines",
    
    # ===== Camera profiles library =====
    "ONVIFProfile",
    "CameraProfilesResult",
    "read_camera_profiles",
    "read_camera_profiles_async",
    
    # ===== PTZ library =====
    "PTZVector",
    "PTZStatus",
    "PTZPreset",
    "PTZCapableProfile",
    "is_ptz_profile",
    "find_ptz_capable_profiles",
    "find_ptz_capable_profiles_async",
    "PTZController",
    
    # ===== Event manager library =====
    "EventCapableCamera",
    "EventFilter",
    "EventNotification",
    "is_event_capable",
    "find_event_capable_cameras",
    "find_event_capable_cameras_async",
    "pull_events_once",
    "stream_events",
]
