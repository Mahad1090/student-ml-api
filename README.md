# student-ml-api

A minimal ML inference service used to demonstrate a professional MLOps delivery
workflow: feature branch → Pull Request → CI → review → merge → semantic tag →
release workflow → versioned image in a container registry.

## API

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness probe + version metadata |
| POST | `/predict` | Body `{"value": <number>}` → `{"input": n, "prediction": 2n}` |

`/health` (v1.1.0):

```json
{
  "status": "healthy",
  "application": "student-ml-api",
  "application_version": "1.1.0",
  "model_version": "model-1"
}
```

## Run locally

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/pytest -q
.venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 5000
```

## Run with Docker

```bash
docker build -t student-ml-api:1.1.0 \
  --build-arg APP_VERSION=$(cat VERSION) \
  --build-arg GIT_COMMIT=$(git rev-parse HEAD) \
  --build-arg BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ) .
docker run -d --name student-ml-api -p 5000:5000 student-ml-api:1.1.0
curl http://localhost:5000/health
```

## Pull the published image

```bash
docker pull ghcr.io/mahad1090/student-ml-api:1.1.0   # or :1.0.0 / :latest
```

## Workflows

| Workflow | Trigger | Does | Never does |
|---|---|---|---|
| `ci.yml` | PR → `main`, push to feature branches | tests, docker build validation | push an image |
| `release.yml` | push tag `v*.*.*` | tests, build, login, tag, push to GHCR | run on PRs |

Full write-up: [docs/MLOPS_WORKFLOW.md](docs/MLOPS_WORKFLOW.md)
