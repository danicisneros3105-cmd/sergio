# Build and share a plugin in 10 minutes

You will write a small plugin that adds a `contar_palabras` tool (word
count), install it, call it from the chat and share it with a pinned hash.

## 1. Create the skeleton

```bash
sergio plugin crear contar-palabras --carpeta ~/plugins
```

This creates `~/plugins/contar-palabras/` with a `plugin.toml` and a
`plugin.py`.

## 2. Write the tool

Replace `plugin.py` with:

```python
from openjarvis.core.types import ToolResult
from openjarvis.tools._stubs import BaseTool, ToolSpec


class ContarPalabras(BaseTool):
    tool_id = "contar_palabras"

    @property
    def spec(self):
        return ToolSpec(
            name="contar_palabras",
            description="Counts the words in a text.",
            parameters={
                "type": "object",
                "properties": {"texto": {"type": "string"}},
                "required": ["texto"],
            },
        )

    def execute(self, texto: str = "", **_):
        return ToolResult(
            tool_name="contar_palabras",
            content=str(len(texto.split())),
            success=True,
        )


def register(api):
    api.tool(ContarPalabras)
```

The tool needs no permissions, so `permissions = []` in `plugin.toml` stays
as it is. A tool that reads files or uses the network must declare it there,
and Sergio shows those permissions before anyone installs the plugin.

## 3. Pack and install

```bash
sergio plugin empaquetar ~/plugins/contar-palabras --salida ~/plugins/dist
sergio plugin instalar ~/plugins/dist/contar-palabras-0.1.0.zip
sergio plugin lista
```

`empaquetar` prints the archive's `sha256`. Keep it: it is how others check
they got exactly your file.

## 4. Use it

Restart the server (or the desktop app) and ask in the chat:

> How many words are in "the quick brown fox jumps"?

The tool call shows up in the chat as `contar_palabras`.

## 5. Share it

Upload the `.zip` anywhere that serves it over HTTPS (a GitHub release works)
and give people the URL and the hash:

```bash
sergio plugin instalar https://example.com/contar-palabras-0.1.0.zip --sha256 <hash>
```

Or publish an index so people can find it with `sergio plugin buscar`:

```json
{"plugins": [{"name": "contar-palabras", "version": "0.1.0",
              "description": "Counts words", "permissions": [],
              "url": "https://example.com/contar-palabras-0.1.0.zip", "sha256": "<hash>"}]}
```

Users add your index with `SERGIO_PLUGIN_INDEX=https://example.com/index.json`.
See [Plugins](../user-guide/plugins.md) for the full rules.
