"""Cine only recognizes the official OAuth connector and its advertised capabilities."""

from openjarvis.creator import cine_ia


class Hub:
    def list(self):
        return [
            {
                "url": "https://lookalike.example/mcp",
                "status": "connected",
                "id": "higgsfield",
            },
            {"url": cine_ia.SERVER_URL, "status": "needs_auth", "id": "logged-out"},
            {"url": cine_ia.SERVER_URL, "status": "connected", "id": "real"},
        ]

    def get(self, server_id):
        assert server_id == "real"
        return {"tools": [{"name": "generate_video", "permission": "ask"}]}

    def tool_schema(self, server_id, tool):
        assert server_id == "real" and tool == "generate_video"
        return {
            "properties": {
                "params": {
                    "properties": {
                        "model": {
                            "anyOf": [
                                {"enum": ["kling3_0", "veo3_1"]},
                                {"type": "string"},
                            ]
                        }
                    }
                }
            }
        }

    def call(self, server_id, tool, args):
        assert server_id == "real" and tool == "get_presets"
        return '[{"id":"p1","name":"Slow dolly"}]'


def test_actual_mcp_state_drives_higgsfield_and_model_inventory():
    hub = Hub()
    assert cine_ia.connector(hub) == "real"
    tools = cine_ia.inventory(hub=hub)
    assert tools[0]["modelos"] == ["kling3_0", "veo3_1"]
    assert tools[0]["permiso"] == "ask"
    assert cine_ia.catalog(hub=hub)[0]["id"] == "p1"
