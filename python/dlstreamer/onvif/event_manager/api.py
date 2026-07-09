# ==============================================================================
# Copyright (C) 2026 Intel Corporation
#
# SPDX-License-Identifier: MIT
# ==============================================================================
"""
dlstreamer.onvif.event_manager — ONVIF Events (PullPoint) engine.

Implements a Python client for the ONVIF Events Service
(http://www.onvif.org/ver10/events/wsdl/event.wsdl) using the
**PullPoint** subscription pattern. Callers do not need to open an
inbound HTTP port — notifications are fetched with long-polling
``PullMessages`` calls, so the engine works behind NAT and firewalls.

Public API:

Data model:
    EventNotification      — parsed NotificationMessage (topic, source,
                             data, timestamp, PropertyOperation)
    EventFilter            — topic expression filter for subscribe()
    EventCapableCamera     — camera descriptor exposing an Events service

Capability discovery (built on :mod:`~dlstreamer.onvif.camera_profiles`
and :mod:`~dlstreamer.onvif.discovery`):
    is_event_capable()
    find_event_capable_cameras()         — sync generator
    find_event_capable_cameras_async()   — async generator

Simple event reading:
    pull_events_once()                   — subscribe, pull one batch, close
    stream_events()                      — async event stream with auto-close

Advanced control:
    :mod:`dlstreamer.onvif.event_manager.engine` provides
    ``OnvifEventEngine`` for callers that need full PullPoint
    subscription lifecycle control.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Optional

from .model import (
    EventCapableCamera,
    EventFilter,
    EventNotification,
)
from .capabilities import (
    find_event_capable_cameras,
    find_event_capable_cameras_async,
    is_event_capable,
)
from .engine import OnvifEventEngine


def pull_events_once(
    hostname: str,
    port: int,
    username: str = "",
    password: str = "",
    verbose: bool = False,
    timeout: str = "PT30S",
    limit: int = 100,
    termination_time: str = "PT1H",
    topic_filter: Optional[EventFilter] = None,
) -> list[EventNotification]:
    """Read one event batch with automatic subscription lifecycle.

    This is the simplest blocking API for events:
    create subscription -> pull once -> close subscription.
    """
    engine = OnvifEventEngine(hostname, port, username, password, verbose)
    try:
        engine.subscribe(termination_time=termination_time, topic_filter=topic_filter)
        return engine.pull(timeout=timeout, limit=limit)
    finally:
        engine.close()


async def stream_events(
    hostname: str,
    port: int,
    username: str = "",
    password: str = "",
    verbose: bool = False,
    timeout: str = "PT30S",
    limit: int = 100,
    termination_time: str = "PT1H",
    topic_filter: Optional[EventFilter] = None,
    renew_every: Optional[float] = 300.0,
) -> AsyncIterator[EventNotification]:
    """Yield events continuously with automatic subscribe/unsubscribe.

    This function hides engine lifecycle details and is the preferred
    async API for long-running event consumption.
    """
    engine = OnvifEventEngine(hostname, port, username, password, verbose)
    try:
        await asyncio.to_thread(
            engine.subscribe,
            termination_time,
            topic_filter,
        )
        async for note in engine.stream(
            timeout=timeout,
            limit=limit,
            renew_every=renew_every,
        ):
            yield note
    finally:
        await asyncio.to_thread(engine.close)

__all__ = [
    # data model
    "EventCapableCamera",
    "EventFilter",
    "EventNotification",
    # capability discovery
    "is_event_capable",
    "find_event_capable_cameras",
    "find_event_capable_cameras_async",
    # simple event reading
    "pull_events_once",
    "stream_events",
]
