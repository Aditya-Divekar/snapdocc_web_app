# SnapDocc production image: FastAPI bot + Tesseract OCR.
# EasyOCR/PyTorch are intentionally NOT included here - see requirements-docker.txt

FROM python:3.11-slim

# Tesseract itself is a system program, not a Python package - install it
# via apt, same idea as installing it on Windows earlier in this project.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (before copying code) so Docker can
# reuse this layer on rebuilds when only your code changes, not deps.
COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

# Now copy the actual application code
COPY app/ app/
COPY README.md .

# Folders the app writes to at runtime
RUN mkdir -p data/uploads data/output

EXPOSE 8000

# Render (and most hosts) assign the port via the $PORT env var at runtime,
# so we fall back to 8000 for local `docker run` testing.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
