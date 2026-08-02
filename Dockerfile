# Pinned, reproducible FungMod environment.
#
# Build:  docker build -t fungmod .
# Version check:      docker run --rm fungmod python -c "import fungmod; print(fungmod.__version__)"
# Reproduce artifacts: docker run --rm -v "$PWD/outputs:/opt/fungmod/outputs" fungmod
#
# The base image tag matches the interpreter used to generate
# requirements-lock.txt. For bit-for-bit reproducibility, pin the base image by
# digest (docker inspect / the registry) instead of by tag.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MPLBACKEND=Agg

WORKDIR /opt/fungmod

# Install the pinned runtime dependency closure first so this layer is cached
# independently of source changes.
COPY requirements-lock.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements-lock.txt

# Install FungMod itself; runtime dependencies are already pinned above.
COPY . .
RUN python -m pip install . --no-deps

# Default command: run the deterministic reproduction workflow.
CMD ["python", "scripts/reproduce.py"]
