# Pinned base image - never use python:latest so builds stay reproducible.
FROM python:3.12-slim

# OCI image metadata. Values are supplied at build time (--build-arg) so the
# published image can be traced back to the commit and version that produced it.
ARG APP_VERSION=dev
ARG GIT_COMMIT=unknown
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="student-ml-api" \
      org.opencontainers.image.description="Minimal ML inference service" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${GIT_COMMIT}" \
      org.opencontainers.image.source="https://github.com/Mahad1090/student-ml-api" \
      org.opencontainers.image.created="${BUILD_DATE}"

WORKDIR /app

# Dependencies are copied and installed before the application code so this
# layer is cached and only rebuilt when requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py VERSION ./

EXPOSE 5000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5000"]
