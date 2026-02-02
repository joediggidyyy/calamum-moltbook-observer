# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runner (Distroless-like)
FROM python:3.11-slim

# Create a non-root user with a high UID to avoid host conflicts
RUN groupadd -g 10001 observer && \
    useradd -u 10001 -g observer -s /sbin/nologin observer

WORKDIR /app

# Copy installed dependencies
COPY --from=builder /install /usr/local

# Copy source code
COPY . /app

# Set ownership to root so the user CANNOT modify them
# The user 'observer' will have read-only access
RUN chown -R root:root /app && \
    chmod -R 555 /app

# Switch to non-root user
USER 10001:10001

# Enforce read-only filesystem at runtime by expecting the volume mount
# CMD will fail if any write is attempted to /app

CMD ["python", "calamum_sampler.py"]
