# Calamum Moltbook Observer — Sandboxed Key Minting Proposal (KEYSMITH) (2026-02-12)

**Author:** ORACL-Prime (GitHub Copilot)

**Type:** Analysis / proposal only (no code changes in this document)

**Purpose:** Replace circular “get an API key from Moltbook” operator guidance with a concrete, sandbox-respecting method that does **not** require running vendor-provided `curl` commands on the host.

**Security posture:** Names-only. Do not paste secrets to chat, logs, job reports, or repo-tracked files.

## Doctrine alignment addendum (2026-02-15)

This proposal is retained as historical design analysis, but it is **not authoritative** where it conflicts with current operator doctrine.

Current doctrine clarification:

- No host directory should contain Moltbook-originated secret material.
- KEYSMITH secret handling must remain sandbox-contained for mint/validation/tamper checks, with direct secure import workflows that avoid host persistence.
- Observer remains Moltbook-facing only from the hardened container lane.

Accordingly, any wording below that implies host-mounted secret export should be interpreted as legacy feasibility exploration, not approved production behavior.

---

## Problem statement

Current operator guidance around obtaining `MOLTBOOK_API_KEY` is too circular and implies host execution. Meanwhile, observed vendor guidance emphasizes “give this command to your agent” and yields a `claim_url` rather than a human registration flow.

Constraints:

- No vendor-provided `curl` or registration commands executed on the operator host.
- All Moltbook registration / key minting should occur from a hardened sandbox.
- The observer should **not** be responsible for minting or retrieving the key.

---

## Proposed role: KEYSMITH (Calamum Keysmith)

**KEYSMITH** is a dedicated, containerized bootstrap utility whose sole job is to mint a Moltbook agent key via the vendor-prescribed flow (e.g., a registration endpoint returning an `api_key` and `claim_url`).

Role boundaries:

- KEYSMITH ≠ observer.
- KEYSMITH runs as a short-lived job in a hardened container.
- KEYSMITH performs network calls only to Moltbook allowlisted domains/endpoints.

Outputs:

- `claim_url` (non-secret): safe to display/log.
- `api_key` (secret): must never be printed to stdout or logs.

**Operator decision (recorded):** Use the "minimal-human" path where humans complete only the vendor claim step (using `claim_url`) while the secret `api_key` is handled entirely by sandbox + secret store tooling.

---

## Secret handoff options (container → operator secret store)

The hard part is not minting the key; it is exporting it from the sandbox without leaking it.

### Option A (preferred): sealed drop file + immediate import + deletion

Dataflow:

1) KEYSMITH writes the minted `api_key` to a file inside the container in a dedicated export directory.
2) That directory is mounted to a host path that is **not tracked** (e.g., under `projects/calamum-moltbook-observer/local_untracked/` or an operator-defined outside-repo location).
3) Operator imports the key into VAULT / OS secret store.
4) Operator deletes the drop file immediately.

Pros:

- Avoids key exposure in terminal output or Docker logs.
- Easy to validate names-only: “drop file created” without disclosing contents.

Cons:

- Brief plaintext-at-rest window on the host (mitigated by short lifetime + immediate deletion).

**Human role boundary (non-negotiable):**

- Humans may see/use `claim_url`.
- Humans must not view/copy/paste/transport `api_key`.
- The import step must be designed so the operator can load the secret into VAULT/OS secret storage without ever displaying the value (names-only evidence only).

### Option B: `docker cp` export (no bind mount)

Container writes secret internally; operator copies it out with a local-only command, imports, then deletes.

Pros:

- No host bind mount.

Cons:

- Still creates a transient secret file on the host.

### Option C (avoid): print the key to stdout

High leak risk into scrollback/transcripts.

---

## Corrected narrative (publish-grade)

1) **Mint**: run KEYSMITH in a hardened container to perform Moltbook agent registration and mint `api_key` + `claim_url`.
2) **Claim**: human uses `claim_url` to claim/associate ownership using the vendor’s workflow.
3) **Store**: operator imports `api_key` into VAULT / OS secret store.
4) **Run**: observer chain consumes `MOLTBOOK_API_KEY` as an environment variable (presence-only checks; never echoed).

This removes the circular “get the key from Moltbook” step and preserves the sandbox boundary.

---

## Notes

- This document intentionally does not embed vendor commands or endpoint details. Those details belong in the sandboxed KEYSMITH implementation + allowlist configuration, not in operator host instructions.

**Status:** Proposed (pending implementation + governance approval if new dependencies are required)
