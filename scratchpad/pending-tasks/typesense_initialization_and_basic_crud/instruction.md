Typesense can run natively as a standalone binary in constrained environments where Docker-in-Docker is unavailable or restricted.

You need to download the Typesense v26.0 Linux AMD64 standalone binary, start it in the background on port 8108 with an API key, and write a script to create a `books` collection, insert a document, and retrieve it in a standard Linux environment.

**Constraints:**
- Must download and execute the native standalone Linux binary (do NOT use Docker).
- The server must be started in the background using the `--data-dir` and `--api-key` flags.
- You must include a polling mechanism to wait for the `/health` endpoint to return `"ok":true` before executing CRUD operations.