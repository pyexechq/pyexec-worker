FROM python:3.11-slim

WORKDIR /app
COPY . /app/worker

RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir /app/worker && \
    rm -rf /app/worker

# Non-root user; add to docker group so it can use the mounted socket
RUN groupadd -g 999 docker 2>/dev/null || true && \
    useradd -m -u 1001 -G docker worker && \
    mkdir -p /home/worker/.pyexec-worker && \
    chown -R worker:worker /home/worker/.pyexec-worker

USER worker

ENTRYPOINT ["pyexec-worker", "start"]
