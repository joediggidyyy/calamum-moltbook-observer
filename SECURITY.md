# Security Policy

## Supported Versions

| Version | Supported | Notes |
| ------- | ------------------ | ------------------------------------------------ |
| 1.0.x   | :white_check_mark: | Active Research Phase (Observer Mode) |
| 0.9.x   | :x: | Legacy Pre-release |

## Reporting a Vulnerability ("The Fail-Closed Pact")

**CRITICAL**: This software contains containment measures ("Glass Box", "Sentinel") designed to prevent malware escape.

If you discover a vulnerability that allows:
1. The container to write to the host filesystem.
2. The agent to bypass the `obfuscator_lib` and leak raw PII.
3. The sentinel to be disabled silently.

Please report it immediately to the project lead (Instructor/TA or Repo Owner) via private channels.

**DO NOT** create a public GitHub issue for containment breaches.

## Threat Model (Scope)
We consider the *input data stream* to be hostile (Toxic Waste). The security boundary is the **Container Runtime**. Anything inside the container is considered "Condemned Space".
