# Job 0015: Stage 4 Activation

> **ID**: CALAMUM_JOB_0015
> **State**: CLOSED
> **Owner**: ORACL-Prime
> **Date**: 2026-02-10

## Overview
This job handles the operational transition to **Stage 4 (Active Magnet)**.
Having validated the threshold (`-0.0451`) in Job 0013/0014, we now update the production configuration and prepare the deployment manifests to enable the "Gated" response mode.

## Objectives
1.  **Configuration**: Ensure `CALAMUM_ACTIVE_MAGNET_THRESHOLD` is supported in `calamum_config.py` (preferred). For compatibility, `ACTIVE_MAGNET_THRESHOLD` may be accepted as a fallback.
2.  **Deployment**: Create a `stage4_active.json` config for the `calamum_observer.py` to consume.
3.  **Safety**: Verify that the "Gated" mode correctly consults the threshold before any active response.
