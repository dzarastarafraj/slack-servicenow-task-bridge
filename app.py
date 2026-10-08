"""Slack Task Bridge — inactive development scaffold.

This is deliberately nonfunctional until the approved ServiceNow Task subtype,
authentication, field mapping, journal access, and idempotency design are implemented.
No Slack or ServiceNow traffic is processed by this scaffold.
"""

from fastapi import FastAPI, HTTPException

app = FastAPI(
    title="Slack Task Bridge",
    description="Internal Slack ↔ ServiceNow Task integration (not configured)",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, object]:
    """Basic health-check only; does not indicate an operational bridge."""
    return {
        "service": "slack-servicenow-task-bridge",
        "status": "scaffold_only",
        "integration_active": False,
    }


@app.post("/api/slack/events")
async def slack_events() -> None:
    """Not implemented: reject events rather than pretending to accept them."""
    raise HTTPException(
        status_code=503,
        detail="Slack Task Bridge is not configured or enabled.",
    )


@app.get("/api/poll-servicenow")
def poll_servicenow() -> None:
    """Not implemented: never run an unauthenticated poller."""
    raise HTTPException(
        status_code=503,
        detail="ServiceNow polling is not configured or enabled.",
    )
