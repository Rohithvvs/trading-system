# NETWORK REQUIREMENTS

## Required Inbound Ports
- **Frontend App**: Port `80` (HTTP) / `443` (HTTPS)
- **Backend API**: Port `8000` (or `443` routed through API gateway proxy)
- **PostgreSQL**: Port `5432` (Only if deploying DB externally, otherwise lock to Docker internal bridge)
- **Redis**: Port `6379` (Only if external cache used)

## Required Outbound Domains
To function correctly, the backend Node must have unimpeded HTTPS outbound access to the following third-party APIs. Firewalls (like AWS Security Groups) must allow `0.0.0.0/0` on port 443, or whitelist these domains specifically:
- `api.fyers.in` (Broker API)
- `api-t1.fyers.in` (Broker websockets / quotes)
- `api.marketaux.com` (News APIs)
- `api.groq.com` (LLM Orchestrator APIs)

## Subnet & DNS Requirements
- Frontend must be able to resolve the backend API through public DNS (`api.trading-system.com`), as the user's browser performs the fetch.
- If using an Internal API Gateway routing `/api` to port 8000, ensure WebSocket headers (`Upgrade: websocket`, `Connection: Upgrade`) are explicitly enabled to allow persistent WS tunnels to `/ws/ticks`.
