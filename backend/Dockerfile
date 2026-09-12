FROM python:3.11-slim

WORKDIR /app

# libgl1/libglib2.0-0: required by opencv-python-headless (a Docling transitive
# dependency) even in headless mode, on Debian slim base images.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install CPU-only PyTorch + torchvision FIRST, together, from PyTorch's own CPU
# wheel index. This index hosts nothing but torch/torchvision/torchaudio, so it's
# safe to scope the whole command to it with --index-url (not --extra-index-url,
# which would leave pip free to resolve a CUDA build from PyPI instead). torch and
# torchvision must be installed together from the SAME index/resolve: torchvision's
# compiled ops (e.g. torchvision::nms) are ABI-matched to one specific torch build,
# so installing them from two different resolutions (CPU index vs. plain PyPI) can
# silently mismatch them — torchvision imports but its custom ops raise
# `RuntimeError: operator torchvision::nms does not exist` the first time a model
# is loaded. Docling/transformers below then find both already installed and
# satisfying their requirement, so pip does not touch them again and never pulls
# the multi-GB nvidia-*/CUDA package tree.
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Production default: no --reload. Local dev compose overrides this command
# explicitly (see docker-compose.yml) to add --reload for the bind-mounted source.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
