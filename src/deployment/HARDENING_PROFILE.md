# Hardening Profile: Calamum Observer (Stage 2)

**Version**: 1.0.0
**Enforcement**: Docker Runtime Flags
**Target**: `calamum-observer:stage2`

## 1. Filesystem Constraints
- **Root Filesystem**: Read-Only (`--read-only`)
- **Volumes**:
  - `/logs`: R/W (Bind mount to host `logs/data/calamum`)
  - `/tmp`: Tmpfs (Optional, 64MB limit, noexec)

## 2. Kernel Capabilities
- **Policy**: DROP ALL
- **Exceptions**: None.
- **Flags**: `--cap-drop ALL`

## 3. User Identity
- **UID**: 10001 (Fixed)
- **GID**: 10001 (Fixed)
- **Privilege Escalation**: Disabled (`--security-opt no-new-privileges:true`)

## 4. Network Policy (Simulation)
In Stage 3 (Canary), this will enforce strict egress.
For Stage 2 (Hardening), we verify the container CAN run without `CAP_NET_ADMIN`.

## 5. Seccomp Profile (Default)
Standard Docker default profile is sufficient for Python runtime. To be tightened in Stage 3 if `ptrace` usage is detected.

## Verification Checklist
1. Try `touch /app/test` -> FAIL (Read-only FS)
2. Try `ping 8.8.8.8` -> FAIL (No capabilities/raw sockets)
3. Try `sudo ls` -> FAIL (No setuid)
