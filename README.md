# tcgplayer-api-toolkit

Unofficial OpenAPI spec and Postman collection for the TCGplayer API (v1.39.0), built from TCGplayer's own developer docs. Not affiliated with TCGplayer. Requires existing API keys; TCGplayer isn't issuing new ones.

## Files

| File                                      | What it is                                                                                                                                                                                                                                                          |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `TCGplayer-OpenAPI-v1.39.json`            | Single OpenAPI 3.0 spec: 80 operations across 77 paths (Stores 47, Catalog 21, Pricing 7, Inventory 3, App 1, Authentication 1) and 129 schemas. Each operation's `x-docs-url` links its source page on [docs.tcgplayer.com](https://docs.tcgplayer.com/reference). |
| `TCGplayer-v1.39.postman_collection.json` | Postman v2.1 collection generated from the spec: all 80 requests, one folder per tag, with placeholder bodies.                                                                                                                                                      |
| `scripts/merge_official.py`               | Script that builds the spec above by merging TCGplayer's per-endpoint OpenAPI definitions.                                                                                                                                                                          |
| `scripts/make_postman.py`                 | Script that converts the spec into the Postman collection.                                                                                                                                                                                                          |

## Differences from the official definitions

TCGplayer publishes one OpenAPI definition per endpoint page. The merged spec adds or changes:

- **Server:** `https://api.tcgplayer.com/{version}` (default `v1.39.0`), per the Getting Started guide. The reference definitions list only `https://api.tcgplayer.com`.
- **Auth:** `POST /token` and a `bearerAuth` security scheme, hand-written from the Getting Started and Store Authorization guides (the reference definitions declare no security).
- **Unversioned root:** `/token` and `/app/authorize/{authCode}` use `https://api.tcgplayer.com` with no version prefix.
- **ProductList By Id / By Key** merged into one operation, `GET /inventory/productlists/{productListIdOrKey}`, since both share one URL template.
- **Unverified assumptions** are flagged with `x-unverified` and a note in the operation description:
  - whether `POST /app/authorize/{authCode}` needs a bearer token;
  - whether `GET /stores/self` takes the version prefix.

## Auth flow

1. `POST /token` with `client_id` (public key) and `client_secret` (private key) → bearer token. Send it as `Authorization: bearer <token>`.
2. For store access: the store generates an authorization code → `POST /app/authorize/{authCode}` returns an `AuthorizationKey` (access token). Request a new token via `POST /token` with header `X-Tcg-Access-Token: <access token>`.
3. `GET /stores/self` with the store-scoped token → store identity / `storeKey`.

## Using the Postman collection

1. Import `TCGplayer-v1.39.postman_collection.json` into Postman.
2. In the collection's variables, set `publicKey` and `privateKey`.
3. Send **Authentication → Request a Bearer Token**. Its test script saves the token to `bearerToken`, which every other request uses.
4. For store calls: set `accessToken` and `storeKey`, turn on the `X-Tcg-Access-Token` header in the token request, and send it again.

## Rebuilding

Save each TCGplayer reference page as Markdown (one `.md` file per endpoint, named after the page slug, containing its `# OpenAPI definition` JSON block) into a directory, then:

```sh
python3 scripts/merge_official.py tcgdocs/ TCGplayer-OpenAPI-v1.39.json
```

Python 3 standard library only. The script asserts that every definition is v1.39.0 and that shared schemas don't conflict.

To regenerate the Postman collection from the spec:

```sh
python3 scripts/make_postman.py TCGplayer-OpenAPI-v1.39.json TCGplayer-v1.39.postman_collection.json
```
