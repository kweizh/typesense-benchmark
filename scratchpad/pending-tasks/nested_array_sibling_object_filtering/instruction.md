Standard dot-notation filtering on nested arrays flattens objects, causing false positive matches across sibling properties.

You need to define a `recipes` collection schema with `enable_nested_fields: true`, index sample recipes containing an `ingredients` array of objects, and execute a search query that matches recipes where a single ingredient object contains both `name:=cheese` and `concentration:<50` in a Typesense environment.

**Constraints:**
- Must use the scoped nested array syntax (e.g., `ingredients.{name:=cheese && concentration:<50}`).
- Do NOT use standard dot-notation filters (e.g., `ingredients.name:=cheese && ingredients.concentration:<50`), as this will fail to scope the boolean logic to individual sibling objects.