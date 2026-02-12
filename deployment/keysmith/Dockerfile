# KEYSMITH sandbox image
# Purpose: mint Moltbook agent keys only inside a sandbox/container lane.
# Security: never prints secrets; writes sealed-drop only to /app/local_untracked (mounted).

FROM python:3.11-slim

WORKDIR /app

# Minimal dependency surface.
COPY deployment/keysmith/requirements.txt /app/deployment/keysmith/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /app/deployment/keysmith/requirements.txt

# Preserve Calamum subtree layout assumptions in keysmith._project_root().
COPY src/keysmith.py /app/src/keysmith.py

# Mark this container as an approved sandbox lane.
ENV KEYSMITH_SANDBOX=1

ENTRYPOINT ["python", "/app/src/keysmith.py"]
