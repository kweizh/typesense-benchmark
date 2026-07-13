Changing the model of an auto-embedding vector field in a single schema update causes validation failures because stored embeddings mismatch the new model's expected dimension size.

You need to write a script to migrate an existing vector field `content_embedding` from the `ts/e5-small` model to the `ts/all-MiniLM-L12-v2` model within a `knowledge_base` collection in a Python or Node.js environment.

**Constraints:**
- Must execute the migration in exactly two separate Collection Update API requests.
- The first request must drop the vector field from the schema, and the second must re-add it with the new model configuration.
- Do NOT drop and recreate the entire collection; the goal is to trigger Typesense to regenerate embeddings in the background on the existing collection.