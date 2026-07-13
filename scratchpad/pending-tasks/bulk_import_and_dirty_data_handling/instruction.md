Importing high volumes of messy data requires robust coercion strategies to avoid massive failure rates on single-document inserts.

You need to write a script to create a `devices` collection with auto-schema detection (`.*` of type `auto`) and bulk ingest a provided dirty dataset (`devices.jsonl`) containing stringified integers using the import endpoint in a Node.js or Python environment.

**Constraints:**
- Must use the bulk import API endpoint (accepting JSONLines), not single-document inserts.
- Must include the `dirty_values: "coerce_or_reject"` parameter to coerce types automatically.
- Must explicitly increase the client connection timeout configuration to handle large bulk payloads without timing out.