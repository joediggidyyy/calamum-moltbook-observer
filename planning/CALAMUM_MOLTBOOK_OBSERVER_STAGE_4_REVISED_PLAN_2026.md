# Stage 4 Plan: Multivariate Detection (Malice + Mimicry)

**Project**: Calamum Moltbook Observer  
**Stage**: 4 (Magnet & Analysis) - *REVISED v2*  
**Date**: 2026-02-10  
**Status**: APPROVED  
**Ref**: projects/calamum-moltbook-observer/planning/

---

## 1. Objective: Dual-Spectrum Detection

Following the relevant Moltbook news analysis, Stage 4 now has a **Dual Detection Mandate**:
1.  **Security (The Shield)**: Detect and isolate *Malicious Behavior* (Phishing, Malware, Injection) regardless of origin (Human or Bot).
2.  **Research (The Mirror)**: Detect "Larper" activity (Human Mimicry) to separate genuine automation from performative noise.

**Hypothesis**: High-risk vectors (TV-3) often correlate with Human Actors ("Larpers"), while low-risk vectors (TV-0) correlate with actual bots. We will test this "Malice-is-Human" hypothesis.

## 2. Methodology: Blind Regression on Obfuscated Data

We retain **"Obfuscation at the Edge"**. 

### 2.1. Feature Extraction (Edge-Side)
New scalar features for calamum_sampler.py:
1.  _latency (Temporal): Time delta between posts. (Humans need sleep/coffee; Bots don't).
2.  _complexity (Entropy): Text variance. (Bots are uniform; Humans are chaotic).
3.  _toxicity (Safety): Presence of obfuscator_lib flagged patterns (links, injection keywords).
4.  _code_density (Context): Technical vs. Conversational ratio.

### 2.2. The Model: DualVectorClassifier
A multi-output model predicting two probabilities per uthor_hash:
- P(Human): The "Turing-Fail" Score.
- P(Malicious): The Threat Score.

docs/policies/pp
Score_{Total} = \alpha * P(Human) + \beta * P(Malicious)
docs/policies/pp

### 2.3. Decision Matrix
| P(Human) | P(Malicious) | Classification | Action |
|---|---|---|---|
| High | High | **Fraud/Scammer** | *Block & Report* |
| High | Low | **Larper (Roleplayer)** | *Filter from Dataset* |
| Low | High | **Rogue Agent** | **Primary Research Target** |
| Low | Low | **Benign Bot** | *Baseline Noise* |

## 3. Implementation Updates

### Phase 4.1: Feature Engineering
*   Update src/calamum_sampler.py to extract _toxicity alongside _latency.

### Phase 4.2: Analysis
*   Train LarpDetectorV1 (Random Forest) on the new dual-label matrix.
*   Prioritize identification of **Rogue Agents** (Low Human / High Malice) as these represent the true "AI Safety" risk, distinct from human trolling.

---
*Authorized by ORACL-Prime*
