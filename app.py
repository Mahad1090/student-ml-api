"""student-ml-api - a minimal ML inference service.

The service exposes a health probe and a numeric prediction endpoint. The
"model" is a deliberately trivial function (it doubles the input); the goal of
this project is to exercise a professional MLOps delivery workflow rather than
model quality.
"""
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, StrictFloat, StrictInt

APPLICATION_NAME = "student-ml-api"


def _read_version() -> str:
    """Return the application version from the VERSION file next to this module."""
    version_file = Path(__file__).resolve().parent / "VERSION"
    try:
        return version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"


APPLICATION_VERSION = _read_version()

app = FastAPI(title=APPLICATION_NAME, version=APPLICATION_VERSION)


class PredictionRequest(BaseModel):
    # StrictInt / StrictFloat reject strings and booleans, so a non-numeric
    # "value" produces a 422 validation error instead of being coerced.
    value: StrictInt | StrictFloat


class PredictionResponse(BaseModel):
    input: float
    prediction: float


@app.get("/health")
def health() -> dict:
    return {
        "status": "healthy",
        "application": APPLICATION_NAME,
        "version": APPLICATION_VERSION,
    }


@app.post("/predict", response_model=PredictionResponse)
def predict(request: PredictionRequest) -> PredictionResponse:
    return PredictionResponse(input=request.value, prediction=request.value * 2)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000)
