"""Merge TCGplayer's per-endpoint OpenAPI definitions (docs.tcgplayer.com, v1.39.0) into one spec.

Usage: python3 scripts/merge_official.py tcgdocs/ out.json
"""
import glob
import json
import re
import sys

src_dir, out = sys.argv[1], sys.argv[2]
METHODS = {"get", "post", "put", "delete", "patch"}
UNVERSIONED = [{"url": "https://api.tcgplayer.com", "description": "Unversioned root"}]

paths, schemas, request_bodies, tags = {}, {}, {}, []
for f in sorted(glob.glob(f"{src_dir}/*.md")):
    m = re.search(r"# OpenAPI definition\s*```json\s*(.*?)```", open(f).read(), re.S)
    if not m:
        continue  # section index pages (catalog.md, stores.md, ...)
    s = json.loads(m.group(1))
    assert s["info"]["version"] == "v1.39.0", f
    for p, item in s["paths"].items():
        for meth, o in item.items():
            assert meth in METHODS and meth not in paths.get(p, {}), (f, meth, p)
            o["x-docs-url"] = "https://docs.tcgplayer.com/reference/" + f.rsplit("/", 1)[1][:-3]
            for t in o.get("tags", []):
                if t not in tags:
                    tags.append(t)
            paths.setdefault(p, {})[meth] = o
    for kind, bucket in (("schemas", schemas), ("requestBodies", request_bodies)):
        for n, v in s.get("components", {}).get(kind, {}).items():
            assert bucket.get(n, v) == v, (kind, n)
            bucket[n] = v

# By-Id and By-Key share one URL template, which OpenAPI treats as a duplicate path.
by_id = paths.pop("/inventory/productlists/{productListId}")["get"]
by_key = paths.pop("/inventory/productlists/{productListKey}")["get"]
assert by_id["responses"] == by_key["responses"]
paths["/inventory/productlists/{productListIdOrKey}"] = {"get": {
    **by_id,
    "summary": "Get ProductList By Id or Key",
    "description": "Returns the ProductList specified by its ProductListId (int64) or ProductListKey (uuid). "
                   "TCGplayer documents these as two operations (Inventory_GetProductListById, "
                   "Inventory_GetProductListByKey) on the same URL template; merged here so the spec is valid.",
    "operationId": "Inventory_GetProductListByIdOrKey",
    "parameters": [{
        "name": "productListIdOrKey", "in": "path", "required": True,
        "description": "ProductListId (integer) or ProductListKey (uuid).",
        "schema": {"oneOf": [{"type": "integer", "format": "int64"}, {"type": "string", "format": "uuid"}]},
    }],
    "x-docs-url": [by_id["x-docs-url"], by_key["x-docs-url"]],
}}

# Unversioned per the guides: store-authorization-workflow posts to https://api.tcgplayer.com/app/authorize/{code}.
paths["/app/authorize/{authCode}"]["post"]["servers"] = UNVERSIONED


def flag_unverified(op, note):
    op["description"] = op.get("description", "").rstrip() + "\n\n**Unverified:** " + note
    op["x-unverified"] = note


flag_unverified(paths["/app/authorize/{authCode}"]["post"],
                "Whether this call requires a bearer token. The reference definition declares no security and "
                "the 2018 Postman collection sent no Authorization header; this spec inherits the global "
                "bearerAuth requirement as an assumption.")
flag_unverified(paths["/stores/self"]["get"],
                "Whether this path takes the /{version} prefix. The Store Authorization guide shows "
                "https://api.tcgplayer.com/stores/self with no version; this spec uses the default versioned "
                "server as an assumption.")

# Not in the reference definitions; from https://docs.tcgplayer.com/docs/getting-started and
# https://docs.tcgplayer.com/docs/store-authorization-workflow.
paths["/token"] = {"post": {
    "tags": ["Authentication"],
    "summary": "Request a Bearer Token",
    "description": "Exchange PUBLIC_KEY / PRIVATE_KEY for a bearer token. To act on a contracted store, also send "
                   "the store's ACCESS_TOKEN (the `AuthorizationKey` from POST /app/authorize/{authCode}) in the "
                   "`X-Tcg-Access-Token` header; the returned token is then store-scoped. Tokens are valid until "
                   "`.expires`; cache and refresh near expiry. Hand-written from the Getting Started and Store "
                   "Authorization guides (not in TCGplayer's reference definitions).",
    "operationId": "Token_Create",
    "servers": UNVERSIONED,
    "security": [],
    "parameters": [{
        "name": "X-Tcg-Access-Token", "in": "header", "required": False,
        "description": "Optional store ACCESS_TOKEN (AuthorizationKey) for store-scoped access.",
        "schema": {"type": "string"},
    }],
    "requestBody": {"required": True, "content": {"application/x-www-form-urlencoded": {
        "schema": {"type": "object", "required": ["grant_type", "client_id", "client_secret"], "properties": {
            "grant_type": {"type": "string", "enum": ["client_credentials"]},
            "client_id": {"type": "string", "description": "PUBLIC_KEY"},
            "client_secret": {"type": "string", "description": "PRIVATE_KEY"},
        }},
    }}},
    "responses": {"200": {"description": "Bearer token issued.", "content": {"application/json": {
        "schema": {"type": "object", "properties": {
            "access_token": {"type": "string", "description": "BEARER_TOKEN; may exceed 300 bytes."},
            "token_type": {"type": "string", "example": "bearer"},
            "expires_in": {"type": "integer", "example": 1209599},
            "userName": {"type": "string", "description": "PUBLIC_KEY the token was issued for."},
            ".issued": {"type": "string"},
            ".expires": {"type": "string"},
        }},
    }}}},
    "x-docs-url": "https://docs.tcgplayer.com/docs/getting-started",
}}

spec = {
    "openapi": "3.0.0",
    "info": {
        "title": "TCGplayer API",
        "version": "v1.39.0",
        "description": (
            "Merged from TCGplayer's per-endpoint OpenAPI definitions at https://docs.tcgplayer.com/reference "
            "(retrieved 2026-10-08). Each operation's `x-docs-url` links its source page.\n\n"
            "**Access:** TCGplayer states it is no longer granting new API access; existing keys only.\n\n"
            "## Additions to the official definitions\n"
            "- `servers` adds the `/{version}` prefix shown in the Getting Started guide "
            "(`https://api.tcgplayer.com/[VERSION]/catalog/categories`); the reference definitions list only "
            "`https://api.tcgplayer.com`.\n"
            "- `POST /token` and `securitySchemes` are hand-written from the Getting Started and Store "
            "Authorization guides; the reference definitions declare no security.\n"
            "- `/token` and `/app/authorize/{authCode}` use the unversioned root, per the guides.\n"
            "- Get ProductList By Id / By Key merged into one operation (same URL template).\n\n"
            "## Auth flow\n"
            "1. `POST /token` with client credentials → bearer token (`Authorization: bearer <token>`).\n"
            "2. Store access: store generates an authorization code → `POST /app/authorize/{authCode}` → "
            "`AuthorizationKey` (ACCESS_TOKEN). Request a new token via `POST /token` with header "
            "`X-Tcg-Access-Token: <ACCESS_TOKEN>`.\n"
            "3. `GET /stores/self` with the store-scoped token → store identity / storeKey. (The guide shows this "
            "URL without a version prefix; whether it requires one is unverified.)"
        ),
    },
    "servers": [{
        "url": "https://api.tcgplayer.com/{version}",
        "variables": {"version": {"default": "v1.39.0", "description": "API version prefix."}},
    }],
    "security": [{"bearerAuth": []}],
    "tags": [{"name": "Authentication"}] + [{"name": t} for t in tags],
    "paths": dict(sorted(paths.items())),
    "components": {
        "securitySchemes": {"bearerAuth": {
            "type": "http", "scheme": "bearer",
            "description": "`access_token` from POST /token. Store-scoped when issued with X-Tcg-Access-Token.",
        }},
        "schemas": dict(sorted(schemas.items())),
        "requestBodies": request_bodies,
    },
}
json.dump(spec, open(out, "w"), indent=2, ensure_ascii=False)
print(len(spec["paths"]), "paths,", sum(len(v) for v in spec["paths"].values()), "operations,",
      len(schemas), "schemas")
