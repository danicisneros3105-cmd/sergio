"""Tool catalogue and credential routes (``/v1/tools``) and the SendBlue
auto-setup helpers (``/v1/channels/sendblue``).

Split out of ``agent_manager_routes.py``; its helpers are looked up on that
module at call time, so behaviour (and anything patched there) is unchanged.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from fastapi import APIRouter, HTTPException, Request

import openjarvis.server.agent_manager_routes as _amr


def build_tools_routers() -> Tuple[APIRouter, APIRouter]:
    """The /v1/tools (catalogue and credentials) and SendBlue setup routers."""
    # ── Tools & credentials ──────────────────────────────────

    tools_router = APIRouter(prefix="/v1/tools", tags=["tools"])

    @tools_router.get("")
    def list_tools(request: Request) -> Dict[str, Any]:
        items = _amr.build_tools_list()
        try:
            mcp_tools, _ = _amr._get_mcp_tools(request.app.state)
            for tool in mcp_tools:
                fn = tool.get("function", {})
                items.append(
                    {
                        "name": fn.get("name", ""),
                        "description": fn.get("description", ""),
                        "category": "mcp",
                        "source": "mcp",
                        "requires_credentials": False,
                        "credential_keys": [],
                        "configured": True,
                    }
                )
        except Exception:
            pass
        return {"tools": items}

    @tools_router.post("/{tool_name}/credentials")
    async def save_tool_credentials(tool_name: str, request: Request) -> Dict[str, Any]:
        from openjarvis import tiers
        from openjarvis.core.credentials import save_credential

        try:
            tiers.require("custom_api")
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

        body = await request.json()
        saved = []
        for key, value in body.items():
            save_credential(tool_name, key, value)
            saved.append(key)
        return {"saved": saved}

    @tools_router.delete("/{tool_name}/credentials/{key}")
    def remove_tool_credential(tool_name: str, key: str) -> Dict[str, Any]:
        from openjarvis.core.credentials import delete_credential

        delete_credential(tool_name, key)
        return {"deleted": key}

    @tools_router.get("/{tool_name}/credentials/status")
    def credential_status(tool_name: str) -> Dict[str, Any]:
        from openjarvis.core.credentials import get_credential_status

        return get_credential_status(tool_name)

    # ── SendBlue auto-setup helpers ─────────────────────────

    sendblue_router = APIRouter(prefix="/v1/channels/sendblue", tags=["sendblue"])

    @sendblue_router.post("/verify")
    async def sendblue_verify(request: Request) -> Dict[str, Any]:
        """Verify SendBlue credentials and return assigned phone lines."""
        body = await request.json()
        api_key_id = body.get("api_key_id", "")
        api_secret_key = body.get("api_secret_key", "")
        if not api_key_id or not api_secret_key:
            raise HTTPException(
                status_code=400,
                detail="api_key_id and api_secret_key are required",
            )

        import httpx

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "https://api.sendblue.co/api/lines",
                    headers={
                        "sb-api-key-id": api_key_id,
                        "sb-api-secret-key": api_secret_key,
                    },
                )
            if resp.status_code == 401:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid SendBlue credentials",
                )
            if resp.status_code >= 400:
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"SendBlue API error: {resp.text[:200]}",
                )
            data = resp.json()
            # data might be a list of lines or {"lines": [...]}
            lines = (
                data
                if isinstance(data, list)
                else data.get("lines", data.get("data", []))
            )
            numbers = []
            for line in lines:
                if isinstance(line, str):
                    num = line
                elif isinstance(line, dict):
                    num = (
                        line.get("number")
                        or line.get("phone_number")
                        or line.get("from_number")
                    )
                else:
                    num = None
                if num:
                    numbers.append(num)
            return {
                "valid": True,
                "numbers": numbers,
                "raw": data,
            }
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to reach SendBlue: {exc}",
            )

    @sendblue_router.post("/register-webhook")
    async def sendblue_register_webhook(request: Request) -> Dict[str, Any]:
        """Auto-register the /webhooks/sendblue endpoint with SendBlue."""
        body = await request.json()
        api_key_id = body.get("api_key_id", "")
        api_secret_key = body.get("api_secret_key", "")
        webhook_url = body.get("webhook_url", "")
        if not webhook_url:
            raise HTTPException(
                status_code=400,
                detail="webhook_url is required",
            )

        import httpx

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.sendblue.co/api/account/webhooks",
                    headers={
                        "sb-api-key-id": api_key_id,
                        "sb-api-secret-key": api_secret_key,
                        "Content-Type": "application/json",
                    },
                    json={
                        "receive": webhook_url,
                    },
                )
            return {
                "registered": resp.status_code < 300,
                "status": resp.status_code,
                "response": resp.json() if resp.status_code < 300 else resp.text[:200],
            }
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to register webhook: {exc}",
            )

    @sendblue_router.post("/test")
    async def sendblue_test(request: Request) -> Dict[str, Any]:
        """Send a test message via SendBlue to verify the setup works."""
        body = await request.json()
        api_key_id = body.get("api_key_id", "")
        api_secret_key = body.get("api_secret_key", "")
        from_number = body.get("from_number", "")
        to_number = body.get("to_number", "")
        if not to_number:
            raise HTTPException(
                status_code=400,
                detail="to_number is required",
            )

        import httpx

        try:
            payload: Dict[str, str] = {
                "number": to_number,
                "content": (
                    "Hello from your OpenJarvis agent! "
                    "Text this number anytime to search your "
                    "personal data. Reply with any question to try it."
                ),
            }
            if from_number:
                payload["from_number"] = from_number

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.sendblue.co/api/send-message",
                    headers={
                        "sb-api-key-id": api_key_id,
                        "sb-api-secret-key": api_secret_key,
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            return {
                "sent": resp.status_code < 300,
                "status": resp.status_code,
                "response": resp.json() if resp.status_code < 300 else resp.text[:200],
            }
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to send test message: {exc}",
            )

    @sendblue_router.get("/health")
    async def sendblue_health(request: Request) -> Dict[str, Any]:
        """Check if the SendBlue channel bridge is wired and ready."""
        sb = getattr(request.app.state, "sendblue_channel", None)
        bridge = getattr(request.app.state, "channel_bridge", None)
        has_bridge = bridge is not None and (
            hasattr(bridge, "_channels") and "sendblue" in bridge._channels
        )
        return {
            "channel_connected": sb is not None,
            "bridge_wired": has_bridge,
            "ready": sb is not None and has_bridge,
        }

    return tools_router, sendblue_router


__all__ = ["build_tools_routers"]
