# ClipHub for Synology

ClipHub is a small, local-first clipboard archive and composer. A Windows helper can post clipboard events to its HTTP API, while Synology stores the durable SQLite database in a bind-mounted folder. The browser UI provides an inbox, pinning, search, archive promotion, and multi-clip composition.

## Synology installation

1. Install **Container Manager** in DSM.
2. Create `/volume1/docker/cliphub` and copy this repository into it.
3. Copy `.env.example` to `.env` and replace `change-me` with a long random API key. Leave the key empty only on a trusted, isolated LAN.
4. In **Container Manager → Project → Create**, select `/volume1/docker/cliphub/compose.yaml` and build the project.
5. Open `http://NAS-IP:8080`. For remote access, put the service behind DSM's HTTPS reverse proxy; do not directly expose port 8080 to the internet.

All durable state is written to `./data/cliphub.db`. Because `./data` is mounted at `/data`, rebuilding or replacing the container does not remove the archive. Back up the complete `data` directory (including SQLite `-wal` and `-shm` files when present).

```bash
cp .env.example .env
docker compose up --build -d
docker compose logs -f cliphub
```

## Windows capture API

Send JSON from a Python or AutoHotkey helper whenever the Windows clipboard changes:

```http
POST /api/clips HTTP/1.1
Host: NAS-IP:8080
Content-Type: application/json
X-API-Key: your-secret

{
  "content": "Text copied on Windows",
  "source_app": "Code.exe",
  "source_window": "README.md — Visual Studio Code",
  "tags": ["project", "documentation"],
  "sensitive": false
}
```

The API supports:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Container health check (does not require a key) |
| `GET`, `POST` | `/api/clips` | Search/list or capture clips |
| `PATCH`, `DELETE` | `/api/clips/{id}` | Pin, archive, tag, mark sensitive, or delete |
| `POST` | `/api/combine` | Combine ordered clip IDs as plain text, bullets, quotes, or JSON |
| `GET`, `POST` | `/api/prompts` | List or save reusable prompt templates |

When `CLIPHUB_API_KEY` is configured, send it in `X-API-Key` for every `/api/*` request except the health check. The web UI remembers a manually set key in browser local storage; in the browser console, run `localStorage.setItem('cliphub-key', 'your-secret')` once and reload.

## Local development

ClipHub deliberately uses only the Python standard library, so development needs no package installation:

```bash
CLIPHUB_DATA_DIR=/tmp/cliphub-data python -m app.server
python -m unittest discover -s tests -v
```

## Storage model

- **Inbox** contains recent working clips.
- **Pinned** clips remain at the top of a listing.
- **Archive** is the promoted long-term collection, kept in the same transactional database.
- **Prompts** stores reusable templates independently from transient clipboard history.
- SQLite uses WAL mode for reliable concurrent reads and writes. Keep the database on the local Synology volume mounted into the container, rather than on an SMB/NFS mount.

