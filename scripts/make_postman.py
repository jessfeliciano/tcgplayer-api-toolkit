"""Convert the merged OpenAPI spec into a Postman v2.1 collection.

Usage: python3 scripts/make_postman.py TCGplayer-OpenAPI-v1.39.json out.json
"""
import json
import re
import sys

src, out = sys.argv[1], sys.argv[2]
spec = json.load(open(src))
schemas = spec["components"]["schemas"]
request_bodies = spec["components"]["requestBodies"]
VERSION = spec["servers"][0]["variables"]["version"]["default"]

TOKEN_TEST = [
    "const body = pm.response.json();",
    "if (body.access_token) {",
    "    pm.collectionVariables.set('bearerToken', body.access_token);",
    "}",
]


def resolve(o):
    while "$ref" in o:
        kind, name = o["$ref"].split("/")[-2:]
        o = (schemas if kind == "schemas" else request_bodies)[name]
    return o


def sample(s, seen=()):
    """Placeholder value built from a schema; stops at recursive refs."""
    if "$ref" in s:
        if s["$ref"] in seen:
            return {}
        return sample(resolve(s), seen + (s["$ref"],))
    if "example" in s:
        return s["example"]
    if "default" in s:
        return s["default"]
    if "enum" in s:
        return s["enum"][0]
    t = s.get("type", "object" if "properties" in s else None)
    if t == "object":
        return {k: sample(v, seen) for k, v in s.get("properties", {}).items()}
    if t == "array":
        return [sample(s.get("items", {}), seen)]
    return {"integer": 0, "number": 0, "boolean": False}.get(t, "")


def body(rb):
    content = resolve(rb)["content"]
    if "application/json" in content:
        return {"mode": "raw", "raw": json.dumps(sample(content["application/json"]["schema"]), indent=2),
                "options": {"raw": {"language": "json"}}}
    props = resolve(content["application/x-www-form-urlencoded"]["schema"]).get("properties", {})
    return {"mode": "urlencoded", "urlencoded": [
        {"key": k, "value": str(sample(v)), "type": "text", "description": v.get("description", "")}
        for k, v in props.items()]}


def request(path, method, op):
    params = op.get("parameters", [])
    segments = [re.sub(r"^\{(.+)\}$", r":\1", seg) for seg in path.strip("/").split("/")]
    if "servers" not in op:
        segments.insert(0, "{{version}}")
    query = [p for p in params if p["in"] == "query"]
    required = "&".join(p["name"] + "=" for p in query if p.get("required"))
    url = {
        "raw": "{{baseUrl}}/" + "/".join(segments) + ("?" + required if required else ""),
        "host": ["{{baseUrl}}"],
        "path": segments,
        "query": [{"key": p["name"], "value": "", "description": p.get("description", ""),
                   "disabled": not p.get("required", False)} for p in query],
        "variable": [{"key": p["name"], "value": "{{storeKey}}" if p["name"] == "storeKey" else "",
                      "description": p.get("description", "")} for p in params if p["in"] == "path"],
    }
    headers = [{"key": p["name"], "value": "", "description": p.get("description", ""),
                "disabled": not p.get("required", False)} for p in params if p["in"] == "header"]
    docs = op["x-docs-url"] if isinstance(op["x-docs-url"], list) else [op["x-docs-url"]]
    req = {
        "method": method.upper(),
        "header": headers,
        "url": url,
        "description": op.get("description", "") + "\n\nDocs: " + ", ".join(docs),
    }
    if "requestBody" in op:
        req["body"] = body(op["requestBody"])
    if op.get("security") == []:
        req["auth"] = {"type": "noauth"}
    item = {"name": op["summary"], "request": req}
    if op["operationId"] == "Token_Create":
        headers[0]["value"] = "{{accessToken}}"
        form = {f["key"]: f for f in req["body"]["urlencoded"]}
        form["client_id"]["value"], form["client_secret"]["value"] = "{{publicKey}}", "{{privateKey}}"
        item["event"] = [{"listen": "test", "script": {"type": "text/javascript", "exec": TOKEN_TEST}}]
    return item


folders = {t["name"]: [] for t in spec["tags"]}
for path, ops in spec["paths"].items():
    for method, op in ops.items():
        folders[op["tags"][0]].append(request(path, method, op))

collection = {
    "info": {
        "name": spec["info"]["title"] + " " + VERSION,
        "description": spec["info"]["description"] + "\n\n## Using this collection\n"
                       "Set `publicKey` and `privateKey`, then send **Authentication → Request a Bearer Token**; "
                       "its test script saves `bearerToken`. For store-scoped calls, set `accessToken` and "
                       "`storeKey`, enable the `X-Tcg-Access-Token` header on the token request, and resend it.",
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "auth": {"type": "bearer", "bearer": [{"key": "token", "value": "{{bearerToken}}", "type": "string"}]},
    "variable": [
        {"key": "baseUrl", "value": "https://api.tcgplayer.com"},
        {"key": "version", "value": VERSION},
        {"key": "publicKey", "value": ""},
        {"key": "privateKey", "value": ""},
        {"key": "bearerToken", "value": ""},
        {"key": "accessToken", "value": ""},
        {"key": "storeKey", "value": ""},
    ],
    "item": [{"name": name, "item": items} for name, items in folders.items() if items],
}
json.dump(collection, open(out, "w"), indent=2, ensure_ascii=False)
print(sum(len(f["item"]) for f in collection["item"]), "requests in", len(collection["item"]), "folders")
