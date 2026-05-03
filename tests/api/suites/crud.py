"""CRUD probe — runs the full lifecycle (list -> create -> read -> update -> delete)
against a single configured object. Mirrors what a user does when they open a
module, create a record, view it, edit it, and delete it.

Configured via:
  CRUD_OBJECT          (e.g. "task", "leads", "accounts")
  CRUD_CREATE_PAYLOAD  (JSON body for POST)
  CRUD_UPDATE_PAYLOAD  (JSON body for PATCH; "id" is injected automatically)
"""
from __future__ import annotations


def run(client, ctx: dict, config) -> None:
    client.set_suite(f"CRUD lifecycle on '{config.crud_object}'")

    if not ctx.get("access_token"):
        client.skip("CRUD suite", "no auth")
        return

    obj = config.crud_object
    base_path = f"/v2/api/{obj}"

    # 1. List
    client.get(base_path, params={"limit": 5})
    client.assert_status(f"GET {base_path}?limit=5 (list)", 200)

    # 2. Create
    client.post(base_path, json_body=config.crud_create_payload)
    res = client.assert_status(f"POST {base_path} (create)", 201, 200)
    if res.status != "pass":
        client.skip("read-back / update / delete", "create failed")
        return

    # The API returns the new id in different shapes depending on the object.
    new_id = (
        client.json_get("data.id")
        or client.json_get("id")
        or client.json_get("data.0.id")
        or client.json_get("result.id")
    )
    if not new_id:
        client.skip("read-back / update / delete", "no id field in create response")
        return
    ctx[f"crud_{obj}_id"] = new_id
    client.assert_predicate(
        "create response includes a record id",
        lambda c: bool(new_id),
        reason_fn=lambda c: "no id returned",
    )

    # 3. Read by id (single)
    client.get(base_path, params={"id": new_id})
    client.assert_status(f"GET {base_path}?id=<new> (read)", 200)

    # 4. Update
    update_body = {**config.crud_update_payload, "id": new_id}
    client.patch(base_path, json_body=update_body)
    client.assert_status(f"PATCH {base_path} (update)", 200, 201)

    # 5. Verify update took effect
    client.get(base_path, params={"id": new_id})
    client.assert_status(f"GET {base_path}?id=<new> (verify update)", 200)
    # Match a single field from the update payload to confirm change applied.
    if config.crud_update_payload:
        first_key, first_val = next(iter(config.crud_update_payload.items()))
        def matches(c):
            body = c.last_json
            if isinstance(body, list) and body:
                return body[0].get(first_key) == first_val
            if isinstance(body, dict):
                if body.get(first_key) == first_val:
                    return True
                data = body.get("data")
                if isinstance(data, list) and data:
                    return data[0].get(first_key) == first_val
                if isinstance(data, dict):
                    return data.get(first_key) == first_val
            return False
        client.assert_predicate(
            f"updated field {first_key!r} reflects new value",
            matches,
            reason_fn=lambda c: f"expected {first_key}={first_val!r}, body={str(c.last_json)[:200]}",
        )

    # 6. Delete (unless the user wants the record kept around)
    if config.keep_created:
        client.skip("delete created record", "KEEP_CREATED=1")
        return

    client.delete(base_path, json_body={"id": new_id})
    client.assert_status(f"DELETE {base_path} (cleanup)", 200, 204)
