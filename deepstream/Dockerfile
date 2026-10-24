# DeepStream 7.1 runtime image (requires NVIDIA driver >= 535 + NVIDIA Container Toolkit on a Linux host
# or WSL2). NOT built or run on the development machine; see docs/testing.md.
FROM nvcr.io/nvidia/deepstream:8.0-triton-multiarch

ENV DEBIAN_FRONTEND=noninteractive
# Python bindings (pyds) are installed by NVIDIA's helper script shipped in the container.
RUN /opt/nvidia/deepstream/deepstream/user_deepstream_python_apps_install.sh --version 1.2.2 || \
    (echo "pyds install helper failed; see docs/troubleshooting.md" && exit 1)
RUN pip3 install --no-cache-dir "psycopg[binary]>=3.1" pyyaml

WORKDIR /app
# Build context is the repository root (see docker-compose.yml).
COPY deepstream/src /app/src
COPY deepstream/config /app/config
COPY scripts/prepare_models.sh /app/prepare_models.sh
ENV PYTHONPATH=/opt/nvidia/deepstream/deepstream-8.0/sources/deepstream_python_apps/pyds/lib/python3.12/site-packages:/app/src
RUN mkdir -p /opt/vds/engines
CMD ["sh", "-c", "bash /app/prepare_models.sh; python3 -m vds.pipeline --config /app/config/pipeline.yml"]
