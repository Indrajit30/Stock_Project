# StockAI Frontend

React + TypeScript + Vite frontend for the AI stock research app.

## Local development

From the workspace root:

```bash
.venv/bin/uvicorn mock_api.server:app --host 127.0.0.1 --port 8001
/Users/arunnair/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node .tools/npm/bin/npm-cli.js run --prefix frontend dev -- --host 127.0.0.1
```

The frontend defaults to `VITE_API_URL=http://localhost:8001` in `.env.local`.
Switch it to `http://localhost:8000` when the real backend is ready.

## Verification

```bash
/Users/arunnair/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node .tools/npm/bin/npm-cli.js run --prefix frontend build
```
