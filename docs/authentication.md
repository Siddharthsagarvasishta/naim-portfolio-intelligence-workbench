# Authentication and role enforcement

nAIM supports three explicit authentication modes.

## Disabled

Set `NAIM_AUTH_MODE=disabled` or `AUTH_MODE=disabled` only for private local development. The backend emits a runtime warning and uses a clearly identified local-development Administrator principal. A public or shared deployment must not use this mode.

## Demo

Set:

```text
NAIM_AUTH_MODE=demo
NAIM_TOKEN_SECRET=<at least 32 random characters>
NAIM_TOKEN_TTL_SECONDS=3600
```

Demo users are created through the setup command; no password is embedded in source or committed configuration. The bootstrap password is supplied through an environment variable or an interactive secret prompt. Passwords are stored as Argon2id hashes. Access tokens use a signed HS256 JWT with issuer, audience, issued-at, not-before, expiry, token version, and unique token ID. Logout persists the token ID in the revocation table. Disabled accounts, superseded token versions, expired tokens, and revoked tokens are rejected.

## OIDC

Set:

```text
NAIM_AUTH_MODE=oidc
NAIM_OIDC_ISSUER=https://identity.example.com/
NAIM_OIDC_AUDIENCE=naim-workbench
NAIM_OIDC_JWKS_URL=https://identity.example.com/.well-known/jwks.json
NAIM_OIDC_ROLE_CLAIM=naim_role
```

The adapter resolves the signing key from the configured JWKS and validates signature, issuer, audience, subject, issued-at, and expiration. The role claim must map to one of the governed nAIM roles. This repository does not claim that a real provider was validated without provider credentials and a reachable identity environment.

## Roles

| Role | Core backend permissions |
|---|---|
| Executive Viewer | View approved reports; download approved artifacts. |
| Portfolio Analyst | View analytics; create investigations and workspaces; download artifacts. |
| Strategy Analyst | Portfolio Analyst permissions plus controlled strategy scenarios. |
| Model Validator | View analytics; approve model versions; download artifacts. |
| Administrator | All governed permissions, including configuration publication and access management. |

The API enforces permissions through dependencies; hiding a control in the browser is not an authorization decision.

## Security notes

- Token and bootstrap secrets must never be logged.
- The local signing secret must be random, deployment-specific, and rotated if exposed.
- Demo mode is suitable for controlled demonstration, not institutional production identity.
- OIDC metadata retrieval requires network access and should be pinned to the institution-approved issuer and audience.
- TLS termination, identity-provider policy, MFA, user lifecycle, and secret storage are deployment responsibilities.
