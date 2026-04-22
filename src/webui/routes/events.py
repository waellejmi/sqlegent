from __future__ import annotations

import asyncio

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from webui.services.docker_events import as_sse, build_docker_snapshot

router = APIRouter()


@router.get("/docker-discovery")
async def docker_discovery_events():
    async def event_stream():
        previous_snapshot = None
        while True:
            snapshot = build_docker_snapshot()
            if previous_snapshot is None:
                yield as_sse(
                    event="status", data={"docker_status": snapshot["docker_status"]}
                )
                yield as_sse(event="containers", data=snapshot)
            elif snapshot != previous_snapshot:
                yield as_sse(event="containers", data=snapshot)
            else:
                yield as_sse(event="heartbeat", data={"ok": True})

            previous_snapshot = snapshot
            await asyncio.sleep(2)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
