# GeoExplore Web Client

This React and Vite client is the local browser interface for GeoExplore geological PDF questions. It submits messages to `/api`, displays final answers, applied metadata filters, and citation metadata returned by the API.

## Local Development

```powershell
npm ci
npm run dev
```

The configured development server is `http://127.0.0.1:5180` and its `/api` proxy targets `http://127.0.0.1:9101`.

## Environment

Copy `.env.example` to `.env` only when a frontend override is required:

```dotenv
VITE_API_BASE=
VITE_CLIENT_ID=
```

Empty values use the client defaults: same-origin `/api` requests and the `geoexplore-browser` client ID.

`VITE_CLIENT_ID` is a local browser identifier, not a credential or an authentication control. Do not expose this client as an authenticated public service without a server-side identity layer.

## Build

```powershell
npm run build
```

The build validates TypeScript and emits a local `dist/` directory. `dist/` and `node_modules/` are local artifacts and are intentionally excluded from the release copy.
