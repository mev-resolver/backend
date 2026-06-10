# Resolver Backend

Python FastAPI backend — detection, mitigation, settlement, attack simulator, WebSocket.

## Quick Start (Simulation Mode — no blockchain needed)

```bash
cp .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Swagger UI: http://localhost:8000/docs

## Deploy Contracts (Live Mode)

```bash
cd contracts && npm install
npx hardhat run scripts/deploy.js --network sepolia
# Copy printed addresses into .env
```

## Key API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET    | /health | Health + stats |
| POST   | /api/dex/swap | Submit swap |
| GET    | /api/dex/price | Current price |
| POST   | /api/attack/manual | One sandwich |
| POST   | /api/attack/auto | Auto loop on/off |
| GET    | /api/stats/summary | Aggregate stats |
| GET    | /api/stats/history | TX history |
| GET    | /api/events/ | Event list |
| GET    | /api/events/replay | Time-range replay |
| WS     | /ws | Live event stream |
