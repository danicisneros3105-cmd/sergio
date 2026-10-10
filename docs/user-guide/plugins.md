# Plugins

Plugins add tools written by other people. Before installing one, Sergio shows
what it is allowed to do and asks.

```bash
sergio plugin buscar clima                  # search the indexes
sergio plugin instalar tipo-de-cambio       # by name
sergio plugin instalar ./mi-plugin-1.0.0.zip
sergio plugin instalar https://…/x.zip --sha256 <hash>
sergio plugin info tipo-de-cambio
sergio plugin lista
sergio plugin desactivar tipo-de-cambio     # or: activar
sergio plugin desinstalar tipo-de-cambio
```

English names work too: `search`, `install`, `uninstall`, `info`, `list`,
`enable`, `disable`, `create`, `pack`.

## Safety rules

- **Permissions are declared** in `plugin.toml` and shown before install. A
  tool that uses a capability its plugin did not declare is refused.
- **Never allowed:** `channel:send` (messaging other people) and
  `system:admin`.
- **No overriding:** a plugin cannot replace one of Sergio's built-in tools.
- **Safe archives:** no absolute paths, `..`, links or executables; at most
  50 MB and 2,000 files.
- **Pinned downloads:** remote index entries must carry a `sha256`, and the
  downloaded file must match it.

## Writing a plugin

```bash
sergio plugin crear mi-plugin       # a ready-to-edit skeleton
sergio plugin empaquetar mi-plugin  # → mi-plugin-0.1.0.zip and its sha256
```

A plugin is a ZIP with:

```
plugin.toml     # name, version, description, entry, permissions
plugin.py       # def register(api): api.tool(MyTool)
assets/         # optional data files
```

```toml
[plugin]
name = "mi-plugin"
version = "0.1.0"
description = "Turns text into uppercase"
entry = "plugin.py"
permissions = []
```

## Indexes

Sergio reads the bundled catalog, `~/.openjarvis/plugins/index.json`, and any
indexes listed in `SERGIO_PLUGIN_INDEX` (comma-separated paths or `https://`
URLs). An index is JSON:

```json
{"plugins": [{"name": "mi-plugin", "version": "0.1.0", "url": "https://…/mi-plugin-0.1.0.zip",
              "sha256": "…", "description": "…", "permissions": [], "premium": false}]}
```

Entries marked `"premium": true` need the Pro plan (see [Plans](plans.md)).
