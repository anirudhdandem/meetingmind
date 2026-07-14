"""FastAPI application entrypoint: wires routers, lifespan, CORS, auth."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import require_user
from app.api.routes import auth, calls, comparison, oauth, retrieval, settings, team, webhooks
from app.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.services import auto_join

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    if not get_settings().cookie_secure:
        log.warning(
            "COOKIE_SECURE is off — session cookies will travel over plain HTTP. "
            "Never run a deployed server this way."
        )
    log.info("MeetingMind API starting up")

    # Calendar auto-join runs inside the API process (like the bots themselves —
    # the manager's registry is in-memory, and prod runs a single worker).
    stop_auto_join = asyncio.Event()
    auto_join_task = (
        asyncio.create_task(auto_join.run_loop(stop_auto_join))
        if get_settings().auto_join_enabled
        else None
    )

    yield

    if auto_join_task is not None:
        stop_auto_join.set()
        auto_join_task.cancel()
        try:
            await auto_join_task
        except asyncio.CancelledError:
            pass
    log.info("MeetingMind API shutting down")


app = FastAPI(title="MeetingMind API", version="0.1.0", lifespan=lifespan)

# Credentialed requests (the session cookie) cannot be sent to a wildcard origin, so
# the allowed frontends are listed explicitly. This is also what stops an arbitrary
# website from reading API responses on a logged-in user's behalf.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Unauthenticated by necessity:
#   auth     — you cannot log in from behind the login wall.
#   webhooks — called by LiveKit, not a browser; it authenticates the request itself
#              by verifying LiveKit's signed token (see routes/webhooks.py).
app.include_router(auth.router)
app.include_router(webhooks.router)

# Everything else needs a full session: password accepted and the emailed code redeemed.
_protected = [Depends(require_user)]
app.include_router(calls.router, dependencies=_protected)
app.include_router(retrieval.router, dependencies=_protected)
app.include_router(comparison.router, dependencies=_protected)
app.include_router(settings.router, dependencies=_protected)
app.include_router(team.router, dependencies=_protected)
app.include_router(oauth.router, dependencies=_protected)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
