# DATA780 Project Proposal: "Blind Sight" - Privacy-Preserving Malicious Agent Detection

**Group Name**: Team Calamum  
**Members**: [Name 1], [Name 2], [Name 3]  
**Date**: 2026-02-02  

---

## 1. Heilmeier's Catechism Analysis

### What are you trying to do?
We aim to train machine learning models to classify "Hostile" or "Toxic" social media activity (e.g., prompt injection, malware distribution) **without ever reading the raw text**. By using only "obfuscated metadata" (content length, graph density, feature flags), we hope to prove that high-accuracy abuse detection is possible while maintaining mathematically guaranteed user privacy.

### How is it done today?
Current moderation systems (e.g., OpenAI, Facebook) rely on "Panopticon" surveillance: they read, decrypt, and store every user message to scan for keywords. This creates massive privacy liabilities and centralizes power.

### What's new in your approach?
We propose **"Blind ML"**:
1.  **Ingestion**: Data is stripped of all semantic content *at the edge* (on the user's device or an ephemeral container) using our `obfuscator_lib`.
2.  **Training**: Models are trained solely on structural metadata (e.g., `content_length`, `has_code_block`, `timestamp_delta`).
3.  **Innovation**: We are testing if structural fingerprints alone are sufficient to separate "Normal Chatter" (TV-0) from "Automated Attacks" (TV-2/TV-3).

### Who cares?
If successful, this architecture allows platforms to detect abuse without violating GDPR/CCPA or exposing researchers to "Toxic Waste" (illegal content). It solves the "Moderator PTSD" problem by removing the need for human review.

### Risks and Payoffs
*   **Risk**: Metadata signal might be too weak to distinguish sophisticated attacks (High False Negative rate).
*   **Payoff**: A privacy-preserving moderation framework that could become a new standard for ethical AI safety.

### Timeline
*   **Week 1-2**: Generate synthetic datasets (100k records) with known ground truth (TV-0 vs TV-3) using `simulate_moltbook_feed`.
*   **Week 3-4**: Feature Engineering (extracting time-series features from JSONL logs).
*   **Week 5-6**: Train Baseline (Logistic Regression) vs. Advanced (Isolation Forest, LSTM).
*   **Week 7**: Evaluate on "Canary Mode" data distributions.

### Evaluation Criteria
*   **Metric**: F1-Score on detecting TV-3 (Toxic) vectors.
*   **Constraint**: False Positive Rate must be < 1% (to avoid censoring benign users).

---

## 2. Technical Specifics

### Methods to Explore
We will compare three approaches to the "Blind Classification" problem:
1.  **Baseline**: Simple Heuristic Rules (e.g., "If length > 1000 and has_link, then Suspicious").
2.  **Supervised**: Random Forest trained on extracted metadata features.
3.  **Unsupervised**: Isolation Forest (Anomaly Detection) to find "weird" behavior without labeled training data.

### Datasets
*   **Synthetic (Ground Truth)**: We will use the `Calamum` generator to produce unlimited labeled data:
    *   `TV-0` (Benign): Normal distribution of lengths/tags.
    *   `TV-3` (Toxic): Anomalous distributions (e.g., short DMs with links, long injection prompts).
*   **Pre-processing**: All data is converted to the `obfuscated_jsonl` schema before the model sees it.

### Evaluation & Implementation
*   **Language**: Python (scikit-learn, pytorch for LSTM).
*   **Infrastructure**: The existing `calamum-observer` container will generate the logs used for training.

---

## 3. Role Allocation (Group of 3)

1.  **Member A (Data Infrastructure)**: Manages the `MockMoltbookClient` generator to produce diverse synthetic datasets (skewed distributions, new attack vectors).
2.  **Member B (Feature Engineer)**: Transforms the raw JSONL logs into numerical feature vectors (e.g., sliding window analysis of `auth_hash` frequency).
3.  **Member C (Modeler)**: Implements and tunes the Random Forest and Isolation Forest models; analyzes the "Privacy-Utility Reference Trade-off".
