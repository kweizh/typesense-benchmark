Secure multi-tenant search architectures require ensuring that frontend search keys cannot query data belonging to other tenants.

You need to index a multi-tenant dataset into a `documents` collection where each record includes a `tenant_id` field, and use the Keys API to programmatically generate a scoped search key restricted to `tenant_id:=tenant_A` in a script environment.

**Constraints:**
- Must use the Typesense Keys API to generate the scoped key dynamically.
- The generated key must inherently restrict queries using the embedded `filter_by` parameter on the backend (so the frontend cannot bypass it).
- Must output the final generated scoped key to a local file named `scoped_key.txt`.