# MLOps Workflow — student-ml-api

This document records the delivery workflow, the configuration choices behind it,
the traceability chain for each release, and the failure analysis required by the
exercise.

---

## 1. Branch protection settings (Part 7)

Configured on `main` via the GitHub API (`PUT /repos/.../branches/main/protection`):

| Setting | Value | Reason |
|---|---|---|
| Require a pull request before merging | on | No direct commits to `main`; every change is reviewed and CI-checked. |
| Required approving reviews | 1 | Forces a second pair of eyes in a team context. |
| Dismiss stale approvals on new commits | on | An approval must reflect the code that actually merges. |
| Require status checks to pass | on | `Unit tests` **and** `Docker build validation` must be green. |
| Require branches up to date before merging | on | The checks run against the post-merge state, not a stale branch. |
| Require conversation resolution | on | No unresolved review threads slip through. |
| Allow force pushes | off | History on `main` cannot be rewritten. |
| Allow deletions | off | `main` cannot be deleted. |
| Enforce for administrators | off (solo repo only) | GitHub does not let an author approve their own PR. In a team this is **on** and the required review is satisfied by another engineer. The merge is still gated on a PR + passing CI. |

Result: development on `main` is only possible through a PR whose CI has passed.

---

## 2. Merge strategy (Part 8)

**Squash and merge**, for both PRs.

Justification:
- Each feature branch carries several iterative WIP commits (PR #1 even contains a
  deliberate break + fix for the CI demonstration). Squashing lands **one atomic,
  reviewed change** per feature on `main`.
- `main` history stays linear and each commit is independently buildable, which
  keeps `git bisect` meaningful.
- The full commit-by-commit history is still preserved and visible on the PR.
- The squash commit message references the PR number (`(#1)`, `(#2)`), so
  `main` → PR is always one hop.

---

## 3. Traceability chain

### Version 1.0.0

```
Pull Request : #1  "feat: prediction API with CI pipeline"
Merge Commit : fa0394b678fb878b4ec9d3ffb4454b26c00ee91d
Git Tag      : v1.0.0
Docker Image : ghcr.io/mahad1090/student-ml-api:1.0.0   (also :fa0394b)
Image Digest : sha256:10000c57bd3adc45a796199743b8b52e858b54d996ca34433f208c6b7b778e4c
```

### Version 1.1.0 (Part 21)

```
Pull Request : #2  "feat: report application and model version on /health"
Merge Commit : 02dc3db8bf199a185b6f0c9d0c454fb599e25e12
Git Tag      : v1.1.0
Docker Image : ghcr.io/mahad1090/student-ml-api:1.1.0   (also :latest, :02dc3db)
Image Digest : sha256:2c9ccbd13d38ad9e8fbb4a067825f32b2c39b09082b31e4372f03332baadcaf5
```

The image also carries the commit as an OCI label:
`org.opencontainers.image.revision=<full commit sha>` — verifiable with
`docker inspect --format '{{json .Config.Labels}}' <image>`.

---

## 4. CI vs Release workflow separation (Part 22)

| | CI (`ci.yml`) | Release (`release.yml`) |
|---|---|---|
| Trigger | `pull_request` → `main`, push to feature branches | push tag `v*.*.*` |
| Jobs | checkout → setup Python → install deps → `pytest` → `docker build` (no push) | checkout → derive version from tag → `pytest` → GHCR login → build → tag → **push** |
| Publishes artifact | **No** | Yes (`<version>`, `latest`, `<short-sha>`) |
| Credentials | none | `GITHUB_TOKEN` with `packages: write` (GitHub-managed secret) |

**Why not publish an image from every PR?**
- A PR is unreviewed, possibly unstable, possibly malicious (forks). Publishing it
  pollutes the registry with throwaway tags and risks someone deploying an
  un-merged change.
- Registry storage and pull bandwidth cost money; most PR builds are never used.
- Publishing should be a deliberate, tagged, auditable event tied to a version —
  not a side effect of opening a PR.
- A leaked or misused push credential in a PR-triggered job is far more dangerous
  than in a tag-triggered one that only maintainers can fire.

The version is derived automatically: `version=${GITHUB_REF_NAME#v}` strips the
`v` from `v1.1.0` → `1.1.0`. Nothing is hard-coded in the workflow.

---

## 5. Image metadata & commit-SHA tag (Parts 23–24)

The Dockerfile adds OCI labels from build args:

```
org.opencontainers.image.title       = student-ml-api
org.opencontainers.image.version     = 1.1.0
org.opencontainers.image.revision    = 02dc3db8bf199a185b6f0c9d0c454fb599e25e12
org.opencontainers.image.source      = https://github.com/Mahad1090/student-ml-api
org.opencontainers.image.created     = <build timestamp>
```

The release workflow publishes a third tag equal to the short commit SHA
(`student-ml-api:02dc3db`) alongside `1.1.0` and `latest`.

**Benefit of a commit-specific tag:** a semantic tag like `1.1.0` is a human
label that could (in a mistake) be re-pushed to point at different content, and
`latest` moves constantly. The commit-SHA tag is 1:1 with an immutable point in
source history — given a running container you can name the exact commit that
built it, and given a commit you can pull exactly that image. It is the reliable
key for debugging "what is actually running in prod?".

---

## 6. Docker layer cache (Part 25)

Dockerfile order:

```dockerfile
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py VERSION ./
```

- **Change only `app.py`** → `requirements.txt` layer and the `pip install` layer
  are unchanged, so Docker reuses them from cache (`---> Using cache`). Only the
  final `COPY app.py` layer and `CMD` metadata are rebuilt. Build takes seconds.
- **Change `requirements.txt`** → that `COPY` layer's checksum changes, which
  invalidates it and **every layer after it**, so `pip install` runs again
  (slow, re-downloads wheels), then `COPY app.py` re-runs too.

`COPY . .` followed by `RUN pip install` is worse because **any** source edit
(a one-character change in `app.py`) changes the `COPY . .` layer and forces a
full `pip install` on every build — wasting minutes of CI time on every commit.
Copying the dependency manifest first isolates the expensive step behind the
rarely-changing file.

---

## 7. Rollback (Part 20)

`1.1.0` is assumed bad. Restore `1.0.0` **without touching source or rebuilding**:

```bash
docker rm -f student-ml-api
docker run -d --name student-ml-api -p 5000:5000 ghcr.io/mahad1090/student-ml-api:1.0.0
curl http://localhost:5000/health
# -> {"status":"healthy","application":"student-ml-api","version":"1.0.0"}
```

Why this beats `git clone && pip install && python app.py`:
- The `1.0.0` image is the **exact bytes** that were tested and previously ran in
  production — same OS packages, same pinned Python, same wheels. A fresh
  `pip install` can resolve different transitive versions today and reintroduce
  bugs or fail outright.
- It is one `docker run`, seconds long, with no build toolchain on the target
  host. `clone + install` needs network, a compiler for some wheels, and minutes.
- Rollback is auditable: "we are running digest `sha256:10000c57…`" is a precise
  claim; "we checked out whatever `main` was around then" is not.

---

## 8. Failure analysis (Part 26)

### Failure 1 — Failed `pytest` blocks the PR (Part 6, deliberate)

| | |
|---|---|
| **Symptom** | PR #1 CI red. `Unit tests` job fails; `Docker build validation` shows *skipped*. PR banner: "Merging is blocked". |
| **Root cause** | `tests/test_app.py::test_health_endpoint` asserted `data["status"] == "wrong"`, but the endpoint returns `"healthy"`. |
| **Evidence** | Actions run `34494638490`: `E AssertionError: assert 'healthy' == 'wrong'` → `FAILED tests/test_app.py::test_health_endpoint`. Commit `test: break health assertion to demonstrate CI failure`. |
| **Correction** | Commit `fix: correct health endpoint test` restored `== "healthy"`. Re-run `34494921761` green, both required checks pass, merge unblocked. |
| **Lesson** | `needs: test` on the docker job means a test failure short-circuits the pipeline; branch protection then makes the failure a hard gate, not a warning. |

### Failure 2 — Missing dependency (deliberately reproduced)

| | |
|---|---|
| **Symptom** | On branch `chore/failure-demo`, CI `Unit tests` job failed during collection; `Docker build validation` skipped (`needs: test`). |
| **Root cause** | `httpx` was removed from `requirements.txt`. FastAPI's `TestClient` is a thin wrapper over `httpx`, so every test that instantiates it fails to import even though `app.py` itself still runs. |
| **Evidence** | Actions run `34498295688`: `E   ModuleNotFoundError: No module named 'httpx'` / `E   RuntimeError: The starlette.testclient module requires the httpx package to be installed.` → `ERROR tests/test_app.py`. |
| **Correction** | Restored `httpx==0.28.1` in `requirements.txt`; branch discarded (never merged). A runtime-only missing dep (e.g. dropping `uvicorn`) would instead pass `pytest` but fail `docker build`'s `CMD` at container start — which is why CI also builds the image. |
| **Lesson** | Pin every direct *and* test-time dependency; CI catches the omission before it reaches `main`. |

### Failure 3 — Wrong / already-allocated container port (observed locally)

| | |
|---|---|
| **Symptom** | `docker run -p 5000:5000 …` → `Error response from daemon: driver failed programming external connectivity … Bind for 0.0.0.0:5000 failed: port is already allocated`. `curl localhost:5000/health` returned a *different* app's JSON (`{"model_version":"1.0","status":"healthy"}`). |
| **Root cause** | Three containers from an unrelated exercise (`mlops-cd-demo`) already published host ports 5000–5002. The new container could not bind, and the port that *was* answering belonged to another service. |
| **Evidence** | `docker ps` showed `0.0.0.0:5000->5000/tcp competent_rhodes`, `…5001 staging-a`, `…5002 staging-b`. Container `student-ml-api` created but stuck in *Created* (never *Up*). |
| **Correction** | Published on a free host port instead: `docker run -p 5005:5000 …`. `curl localhost:5005/health` then returned the correct `student-ml-api` payload. (Alternative: `docker stop staging-a staging-b competent_rhodes`.) |
| **Lesson** | The container port (`EXPOSE 5000`, the `--port 5000` in `CMD`) is fixed by the image; the **host** side of `-p host:container` is what collides. Always verify *which* process answers a port before trusting a health check. |

### (Related) Why binding to `127.0.0.1` would break the container

If `app.py` ran `uvicorn.run(app, host="127.0.0.1", …)`, the server would only
accept connections from inside the container's own network namespace. `docker run
-p 5005:5000` forwards from the host to the container's *external* interface, so
`curl localhost:5005/health` from the host would get *connection reset*. This is
why the app and the `CMD` both use `--host 0.0.0.0`.

---

## 9. Viva answers (condensed)

1. **Why not push directly to `main`?** No review, no CI gate, no audit trail;
   a bad commit is immediately "production". PRs make every change reviewed,
   tested and revertible as a unit.
2. **Purpose of a PR beyond merging?** Code review, discussion, a CI checkpoint,
   a documented rationale, and a durable link between a change and why it was made.
3. **Why CI before merge?** To keep `main` always green. Catching a failure after
   merge means everyone else pulls broken code and the fix needs its own PR.
4. **Image vs container?** An image is an immutable, layered filesystem +
   metadata (a build artifact). A container is a running (or stopped) instance of
   an image with its own writable layer, PID, network and lifecycle.
5. **Why version images?** So a deploy names an exact artifact, rollbacks are
   possible, and "what's running?" has a precise answer.
6. **Why is `latest` insufficient?** It is a moving pointer — it means different
   bytes over time, isn't recorded anywhere, and two machines pulling "latest" a
   day apart can run different code. No traceability.
7. **Why promote the same artifact rather than rebuild?** A rebuild from source
   can pull different transitive dependencies / base-image patches and produce a
   subtly different image that was never tested. Promotion ships the *tested* bits.
8. **Purpose of a container registry?** A versioned, access-controlled store that
   distributes immutable image artifacts (by tag and by digest) to any
   environment.
9. **CI vs release workflow?** CI validates proposed changes on PRs and publishes
   nothing. Release runs on a version tag and is the only thing that builds and
   pushes a published image.
10. **Why secrets for registry credentials?** Hard-coded credentials in YAML are
    in git history forever, visible to anyone with read access, and cannot be
    rotated cleanly. Secrets are injected at runtime, masked in logs, scoped.
11. **How to find the commit for an image?** The `<short-sha>` tag, or
    `docker inspect` → `org.opencontainers.image.revision` label.
12. **Why does layer ordering affect CI/CD speed?** A changed layer invalidates
    the cache for itself and everything after it. Put slow, rarely-changing steps
    (dependency install) before fast, frequently-changing ones (app code).
13. **Rollback 1.1.0 → 1.0.0?** `docker run ghcr.io/…/student-ml-api:1.0.0` — the
    old image is still in the registry; no code change, no rebuild.
14. **Git tag vs Docker image tag?** The Git tag (`v1.1.0`) marks a commit in
    source history and *triggers* the release; the Docker tag (`1.1.0`) labels the
    resulting image in the registry. The workflow derives the second from the first.
15. **App version vs model version changing independently?** You need to record
    *both* per release (done here via `application_version` + `model_version`),
    or you cannot reproduce a prediction: the same code with a different model, or
    the same model behind different code, are different systems. It also
    multiplies the test matrix and complicates rollback (roll back code, model,
    or both?).
