# ADR 002: Authentication and Request Signing Scheme

## Status
Accepted

## Context
The system interfaces with two distinct client classes:
1. **Web Users**: Interacting via browsers with dashboard analytics, configuration, and manual overrides.
2. **EA Terminals**: Running in MetaTrader 5 executing sensitive financial transactions.

A compromised communication channel or replay attack could cause unauthorized trades, unauthorized parameter modifications, or fake telemetry injection.

## Decision
We enforce a split authentication architecture:

### 1. Web Application Authentication (`/app/v1/*`)
- Passwords hashed using **Argon2id** (`pwdlib[argon2]`).
- Session tokens are random 256-bit entropy values stored as SHA-256 hashes in PostgreSQL / Redis with active TTL.
- Cookies configured with `HttpOnly`, `Secure`, `SameSite=Strict`, and `Path=/`.
- Per-user and per-IP sliding window rate limiting backed by Redis.

### 2. EA Terminal Authentication (`/ea/v1/*`)
- **One-Time Pairing**:
  - The web application generates a single-use, 8-character base-32 pairing code with a 10-minute TTL.
  - The EA submits `POST /ea/v1/pair` with `pairingCode` and terminal metadata.
  - Backend returns a newly generated 256-bit `deviceToken` (HMAC secret). This token is **shown once** and stored in the database exclusively as a SHA-256 hash.
  - The EA persists the secret locally in `MQL5/Files/` in the MT5 sandboxed filesystem.
- **HMAC-SHA256 Request Signing**:
  Every subsequent request to `/ea/v1/*` must supply:
  - `X-EA-Device-Token`: The SHA-256 device identifier / public token header.
  - `X-EA-Timestamp`: Unix epoch timestamp in seconds.
  - `X-EA-Nonce`: Cryptographically random UUID/string (16–64 chars).
  - `X-EA-Signature`: `HMAC-SHA256(secret, CanonicalRequest)`
- **Canonical Request Formulation**:
  $$\text{CanonicalRequest} = \text{METHOD} + \text{"\n"} + \text{PATH} + \text{"\n"} + \text{TIMESTAMP} + \text{"\n"} + \text{NONCE} + \text{"\n"} + \text{SHA256}(\text{BODY})$$
- **Replay Protection & Anti-Drift**:
  - Rejects any request with $|\text{CurrentTime} - \text{Timestamp}| > 30\text{ seconds}$.
  - Nonces are stored in Redis (`SET nonce EX 60 NX`). If a nonce is reused, the request is immediately rejected with HTTP 401.

### 3. Log Scrubbing & Privacy
- Full request bodies, device tokens, and HMAC secrets are strictly excluded from all application logs and telemetry.

## Rejected Alternatives
1. **JWTs for EA Terminals**:
   - *Rejected* because JWTs cannot be instantly revoked without centralized blacklisting, and raw JWT signatures do not verify body digests against tampering.
2. **Plain Bearer API Keys**:
   - *Rejected* because intercepted bearer tokens allow full replay and injection attacks without proof-of-possession of the signing secret.

## Consequences
- **Positive**: Complete replay attack immunity; instantaneous device revocation; cryptographically verified payload integrity; zero credential leakage in logs.
- **Negative**: Requires MQL5 native implementation of HMAC-SHA256 request canonicalization using `CryptEncode()`.
