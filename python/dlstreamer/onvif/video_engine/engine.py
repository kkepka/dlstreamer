# ==============================================================================
# Copyright (C) 2026 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================
"""Runtime engine for ONVIF discovery and DL Streamer pipeline orchestration."""

from __future__ import annotations

import json
from contextlib import suppress
import subprocess
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional, Sequence

from ..discovery import discover_onvif_cameras

from .model import (
    CameraEventDefinition,
    CameraIdentity,
    CameraRuntimeState,
    PipelineBinding,
    VideoEngineEvent,
    as_camera_identity,
    pipeline_list,
)

CallbackType = Callable[[VideoEngineEvent], None]
PipelineRunnerType = Callable[[PipelineBinding], subprocess.Popen[Any]]


class VideoEngine:
    """Coordinate discovery, camera matching, pipeline control and events."""

    def __init__(
        self,
        config_path: str | Path | None = None,
        *,
        discovery_time: int = 60,
        timeout: int = 120,
        verbose: bool = False,
        pipeline_runner: Optional[PipelineRunnerType] = None,
    ) -> None:
        self._config_path = Path(config_path) if config_path is not None else None
        self._discovery_time = max(1, int(discovery_time))
        self._timeout = max(1, int(timeout))
        self._verbose = verbose
        self._pipeline_runner = pipeline_runner

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._discovery_thread: Optional[threading.Thread] = None
        self._reaper_thread: Optional[threading.Thread] = None

        self._bindings: list[PipelineBinding] = []
        self._binding_lookup: Dict[str, PipelineBinding] = {}
        self._event_definitions: Dict[str, list[CameraEventDefinition]] = {}
        self._camera_states: Dict[str, CameraRuntimeState] = {}
        self._active_processes: Dict[str, subprocess.Popen[Any]] = {}
        self._callbacks: list[CallbackType] = []

        if self._config_path is not None:
            self.load_config(self._config_path)

    def load_config(self, config_path: str | Path) -> None:
        path = Path(config_path)
        if not path.exists():
            with self._lock:
                self._bindings = []
                self._binding_lookup = {}
                self._config_path = path
            return

        payload = json.loads(path.read_text(encoding="utf-8"))
        bindings = self._parse_bindings(payload)
        with self._lock:
            self._bindings = bindings
            self._binding_lookup = {binding.binding_id: binding for binding in bindings}
            self._config_path = path

    def save_config(self) -> None:
        if self._config_path is None:
            raise ValueError("no configuration path was set")

        with self._lock:
            payload = {"pipelines": [binding.to_dict() for binding in self._bindings]}
        self._config_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def start(self) -> None:
        self.discovery_start()
        self._start_reaper()

    def stop(self) -> None:
        self.discovery_stop()
        self._stop_reaper()
        self._stop_all_processes()

    def destroy(self) -> None:
        self.stop()
        with self._lock:
            self._bindings = []
            self._binding_lookup = {}
            self._event_definitions.clear()
            self._camera_states.clear()
            self._active_processes.clear()
            self._callbacks.clear()

    def discovery_start(self) -> None:
        with self._lock:
            if self._discovery_thread is not None and self._discovery_thread.is_alive():
                return
            self._stop_event.clear()
            self._discovery_thread = threading.Thread(target=self._discovery_loop, name="video-engine-discovery", daemon=True)
            self._discovery_thread.start()

    def discovery_stop(self) -> None:
        self._stop_event.set()
        thread = None
        with self._lock:
            thread = self._discovery_thread
            self._discovery_thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    def setTimeout(self, sec: int) -> None:
        self._timeout = max(1, int(sec))

    def getTimeout(self) -> int:
        return self._timeout

    def setDiscoveryTime(self, sec: int) -> None:
        self._discovery_time = max(1, int(sec))

    def getDiscoveryTime(self) -> int:
        return self._discovery_time

    def register_callback(self, callback: CallbackType) -> None:
        with self._lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)

    def unregister_callback(self, callback: CallbackType) -> None:
        with self._lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def list_camera_pipeline_pairs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [binding.to_dict() for binding in self._bindings]

    def get_pipeline_for_camera(
        self,
        hostname: str,
        port: int,
        mac: str | None = None,
    ) -> list[dict[str, Any]]:
        identity = CameraIdentity(hostname, int(port), mac)
        with self._lock:
            matches = [binding.to_dict() for binding in self._bindings if self._binding_matches(binding, identity)]
        return matches

    def set_camera_pipeline(
        self,
        hostname: str,
        port: int,
        pipeline: Sequence[str] | str,
        *,
        mac: str | None = None,
        binding_id: str | None = None,
        events: Iterable[str] | None = None,
        persist: bool = False,
    ) -> PipelineBinding:
        identity = CameraIdentity(hostname, int(port), mac)
        normalized = pipeline_list(pipeline)
        event_tuple = tuple(str(item) for item in (events or ()))
        with self._lock:
            resolved_binding_id = binding_id or f"{identity.key()}:{len(self._bindings)}"
            binding = PipelineBinding(identity, normalized, resolved_binding_id, event_tuple)
            self._bindings.append(binding)
            self._binding_lookup[resolved_binding_id] = binding
        if persist:
            self.save_config()
        return binding

    def set_camera_event(
        self,
        hostname: str,
        port: int,
        event_name: str,
        *,
        mac: str | None = None,
        topic_filter: str | None = None,
        renew_every: float | None = None,
        **metadata: Any,
    ) -> CameraEventDefinition:
        identity = CameraIdentity(hostname, int(port), mac)
        definition = CameraEventDefinition(event_name, identity, topic_filter, renew_every, dict(metadata))
        with self._lock:
            self._event_definitions.setdefault(identity.key(), []).append(definition)
        return definition

    def list_camera_events(self, hostname: str, port: int, mac: str | None = None) -> list[dict[str, Any]]:
        identity = CameraIdentity(hostname, int(port), mac)
        with self._lock:
            definitions = self._event_definitions.get(identity.key(), [])
            return [asdict(item) for item in definitions]

    def add_pipeline(self, binding: PipelineBinding, *, start: bool = True) -> PipelineBinding:
        """Register a pipeline binding and optionally start it immediately.

        Replaces any existing binding sharing the same ``binding_id`` so the
        operation is idempotent for event-driven callers.
        """
        with self._lock:
            self._bindings = [b for b in self._bindings if b.binding_id != binding.binding_id]
            self._bindings.append(binding)
            self._binding_lookup[binding.binding_id] = binding
        if start:
            self._start_pipeline_if_needed(binding)
        return binding

    def remove_pipeline(self, binding_id: str) -> None:
        """Stop a running pipeline (if any) and forget its binding."""
        self._stop_pipeline(binding_id)
        with self._lock:
            self._bindings = [b for b in self._bindings if b.binding_id != binding_id]
            self._binding_lookup.pop(binding_id, None)

    def replace_pipeline(
        self,
        binding_id: str,
        pipeline: Sequence[str] | str,
        *,
        camera: CameraIdentity | None = None,
        profile_name: str | None = None,
        events: Iterable[str] | None = None,
        start: bool = True,
    ) -> PipelineBinding:
        """Restart-based modification: stop, swap the command, start again.

        Preserves the existing binding's camera/profile/events when they are
        not overridden. Falls back to ``camera`` when the binding is new.
        """
        with self._lock:
            current = self._binding_lookup.get(binding_id)
        target_camera = camera or (current.camera if current is not None else None)
        if target_camera is None:
            raise ValueError("replace_pipeline requires a known binding or an explicit camera")

        self._stop_pipeline(binding_id)

        event_tuple = (
            tuple(str(item) for item in events)
            if events is not None
            else (current.events if current is not None else ())
        )
        resolved_profile = profile_name if profile_name is not None else (current.profile_name if current else None)
        new_binding = PipelineBinding(target_camera, pipeline_list(pipeline), binding_id, event_tuple, resolved_profile)

        with self._lock:
            self._bindings = [b for b in self._bindings if b.binding_id != binding_id]
            self._bindings.append(new_binding)
            self._binding_lookup[binding_id] = new_binding
        if start:
            self._start_pipeline_if_needed(new_binding)
        return new_binding

    def restart_pipeline(self, binding_id: str) -> None:
        """Stop and start the pipeline for an existing binding unchanged."""
        with self._lock:
            binding = self._binding_lookup.get(binding_id)
        if binding is None:
            return
        self._stop_pipeline(binding_id)
        self._start_pipeline_if_needed(binding)

    def get_active_cameras(self) -> list[dict[str, Any]]:
        with self._lock:
            return [self._runtime_state_to_dict(state) for state in self._camera_states.values()]

    def get_active_pipelines(self) -> list[dict[str, Any]]:
        with self._lock:
            active: list[dict[str, Any]] = []
            for binding_key, process in self._active_processes.items():
                active.append(
                    {
                        "binding_key": binding_key,
                        "pid": process.pid,
                    }
                )
            return active

    def _parse_bindings(self, payload: Any) -> list[PipelineBinding]:
        if isinstance(payload, dict):
            entries = payload.get("pipelines", [])
        elif isinstance(payload, list):
            entries = payload
        else:
            raise ValueError("video_engine configuration must be a mapping or a list")

        bindings: list[PipelineBinding] = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise ValueError("each pipeline entry must be a mapping")

            camera_payload = entry.get("camera", entry)
            identity = as_camera_identity(camera_payload)
            pipeline_value = entry.get("pipeline")
            if pipeline_value is None:
                raise ValueError("pipeline entry requires a pipeline field")

            binding_id = str(entry.get("binding_id") or entry.get("pipeline_id") or f"{identity.key()}:{index}")
            events = tuple(str(item) for item in entry.get("events", []))
            profile_name = entry.get("profile_name")
            bindings.append(PipelineBinding(identity, pipeline_list(pipeline_value), binding_id, events, profile_name))
        return bindings

    def _binding_matches(self, binding: PipelineBinding, identity: CameraIdentity) -> bool:
        if binding.camera.hostname != identity.hostname:
            return False
        if int(binding.camera.port) != int(identity.port):
            return False
        if binding.camera.mac and identity.mac:
            return binding.camera.mac == identity.mac
        return True

    def _discovery_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                for camera in discover_onvif_cameras(verbose=self._verbose):
                    if self._stop_event.is_set():
                        break
                    self._handle_camera_seen(camera)
            except (OSError, RuntimeError, ValueError) as exc:
                self._emit("discovery_error", CameraIdentity("unknown", 0), {"error": str(exc)})

            if self._stop_event.wait(self._discovery_time):
                break

    def _start_reaper(self) -> None:
        with self._lock:
            if self._reaper_thread is not None and self._reaper_thread.is_alive():
                return
            self._stop_event.clear()
            self._reaper_thread = threading.Thread(target=self._reaper_loop, name="video-engine-reaper", daemon=True)
            self._reaper_thread.start()

    def _stop_reaper(self) -> None:
        self._stop_event.set()
        thread = None
        with self._lock:
            thread = self._reaper_thread
            self._reaper_thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    def _reaper_loop(self) -> None:
        while not self._stop_event.is_set():
            self._reap_stale_cameras()
            if self._stop_event.wait(max(1, min(self._timeout, self._discovery_time))):
                break

    def _reap_stale_cameras(self) -> None:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        stale_keys: list[str] = []
        with self._lock:
            for key, state in self._camera_states.items():
                if (now - state.last_seen).total_seconds() > self._timeout:
                    stale_keys.append(key)

        for key in stale_keys:
            self._handle_camera_lost(key)

    def _handle_camera_seen(self, camera: dict[str, Any]) -> None:
        identity = as_camera_identity(camera)
        key = identity.key()
        matched_bindings: list[PipelineBinding]
        with self._lock:
            matched_bindings = [binding for binding in self._bindings if self._binding_matches(binding, identity)]
            state = self._camera_states.get(key)
            if state is None:
                state = CameraRuntimeState(identity)
                self._camera_states[key] = state
            state.status = "matched" if matched_bindings else "discovered"
            state.error = None
            state.touch()

        if self._verbose:
            print(f"[video_engine] Camera discovered: {key}, matched bindings: {len(matched_bindings)}")
            for binding in matched_bindings:
                print(f"[video_engine]   -> binding '{binding.binding_id}' (profile: {binding.profile_name})")

        self._emit("camera_seen", identity, {"matched": bool(matched_bindings)})

        for binding in matched_bindings:
            self._start_pipeline_if_needed(binding)
            self._bind_camera_to_binding(key, binding.binding_id)

    def _bind_camera_to_binding(self, camera_key: str, binding_id: str) -> None:
        with self._lock:
            state = self._camera_states.get(camera_key)
            if state is None:
                return
            if binding_id in state.pipeline_binding_ids:
                return
            state.pipeline_binding_ids = tuple((*state.pipeline_binding_ids, binding_id))

    def _handle_camera_lost(self, camera_key: str) -> None:
        with self._lock:
            state = self._camera_states.pop(camera_key, None)
            if state is None:
                return
            binding_ids = list(state.pipeline_binding_ids)
        for binding_id in binding_ids:
            self._stop_pipeline(binding_id)
        self._emit("camera_lost", state.camera, {})

    def _start_pipeline_if_needed(self, binding: PipelineBinding) -> None:
        binding_key = binding.binding_id
        with self._lock:
            if binding_key in self._active_processes:
                return

        process = self._spawn_pipeline(binding)
        with self._lock:
            self._active_processes[binding_key] = process

        self._emit("pipeline_started", binding.camera, {"binding_id": binding_key, "pid": process.pid})

    def _spawn_pipeline(self, binding: PipelineBinding) -> subprocess.Popen[Any]:
        if self._pipeline_runner is not None:
            return self._pipeline_runner(binding)

        command = self._resolve_pipeline_command(binding)
        if self._verbose:
            if isinstance(command, str):
                print(f"[video_engine] Spawning pipeline for {binding.camera.key()}: {command[:100]}...")
            else:
                cmd_str = " ".join(str(c) for c in list(command)[:5])
                print(f"[video_engine] Spawning pipeline for {binding.camera.key()}: {cmd_str}...")

        # Log pipeline stdout/stderr to /tmp for debugging
        log_file = open(f"/tmp/video_engine_pipeline_{binding.binding_id.replace(' ', '_')}.log", "w")
        if self._verbose:
            print(f"[video_engine] Logging pipeline output to: {log_file.name}")

        if isinstance(command, str):
            return subprocess.Popen(command, shell=True, stdout=log_file, stderr=subprocess.STDOUT)
        return subprocess.Popen(list(command), stdout=log_file, stderr=subprocess.STDOUT)

    def _resolve_pipeline_command(self, binding: PipelineBinding) -> Sequence[str] | str:
        """Resolve {rtsp_url} placeholder in pipeline using camera profile."""
        command = binding.pipeline
        if isinstance(command, str):
            pipeline_str = command
        else:
            pipeline_str = " ".join(str(c) for c in command)

        # If no {rtsp_url} placeholder or no profile_name, return as-is
        if "{rtsp_url}" not in pipeline_str or not binding.profile_name:
            return command

        if self._verbose:
            print(f"[video_engine] Resolving {{rtsp_url}} placeholder for profile '{binding.profile_name}'")

        # Try to resolve RTSP URL from camera profile
        rtsp_url = self._get_profile_rtsp_url(binding.camera, binding.profile_name)
        if rtsp_url is None:
            if self._verbose:
                print(f"[video_engine] ERROR: Could not resolve RTSP URL for profile {binding.profile_name}")
            return command

        if self._verbose:
            print(f"[video_engine] Resolved RTSP URL: {rtsp_url}")

        # Replace placeholder
        if isinstance(command, str):
            return command.replace("{rtsp_url}", rtsp_url)
        else:
            return tuple(str(c).replace("{rtsp_url}", rtsp_url) for c in command)

    def _get_profile_rtsp_url(self, camera: CameraIdentity, profile_name: str) -> Optional[str]:
        """Get RTSP URL for a specific profile from camera profile data."""
        try:
            from ..camera_profiles import read_camera_profiles
            username = ""
            password = ""
            cameras = [{"hostname": camera.hostname, "port": camera.port}]
            for result in read_camera_profiles(cameras, username=username, password=password):
                if not result.ok:
                    continue
                for profile in result.profiles:
                    if profile.name == profile_name:
                        return profile.rtsp_url
        except Exception as exc:
            if self._verbose:
                print(f"Error resolving profile URL: {exc}")
        return None

    def _stop_pipeline(self, binding_id: str) -> None:
        with self._lock:
            process = self._active_processes.pop(binding_id, None)
            binding = self._binding_lookup.get(binding_id)
        if process is None:
            return

        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

        camera = binding.camera if binding is not None else CameraIdentity("unknown", 0)
        self._emit("pipeline_stopped", camera, {"binding_id": binding_id, "pid": process.pid})

    def _stop_all_processes(self) -> None:
        with self._lock:
            binding_ids = list(self._active_processes.keys())
        for binding_id in binding_ids:
            self._stop_pipeline(binding_id)

    def _emit(self, kind: str, camera: CameraIdentity, details: Dict[str, Any]) -> None:
        with self._lock:
            callbacks = list(self._callbacks)
        event = VideoEngineEvent(kind, camera, details)
        for callback in callbacks:
            with suppress(Exception):
                callback(event)

    def _runtime_state_to_dict(self, state: CameraRuntimeState) -> Dict[str, Any]:
        return {
            "camera": {
                "hostname": state.camera.hostname,
                "port": state.camera.port,
                "mac": state.camera.mac,
            },
            "status": state.status,
            "last_seen": state.last_seen.isoformat(),
            "pipeline_binding_ids": list(state.pipeline_binding_ids),
            "error": state.error,
        }


__all__ = ["VideoEngine"]
