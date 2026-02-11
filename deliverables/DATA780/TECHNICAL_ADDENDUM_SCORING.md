# Technical Addendum: Anomaly Scoring Mechanics

The **Anomaly Score** used in this project is derived from the **Isolation Forest** algorithm (`scikit-learn` implementation). This addendum explains the mathematical derivation of the score and its interpretation.

### 1. The Core Concept: Isolation Depth
The fundamental premise of Isolation Forest is that *anomalies are easier to isolate* than normal points. In a random binary search tree (iTree) constructed by recursively selecting a random feature and a random split value:
*   **Anomalies** (rare, distinct) tend to land in leaves very close to the root (short path length).
*   **Normal points** (common, clustered) require many splits to be isolated (long path length).

### 2. Implementation Math (`scikit-learn`)
The model builds an ensemble of $t$ isolation trees. For a given sample $x$, the path length $h_i(x)$ is calculated for each tree $i$.

The raw average path length is $E(h(x))$. However, `scikit-learn`'s `decision_function` returns a normalized, shifted score:

$$ s = 2^{ -\frac{E(h(x))}{c(n)} } $$

Where:
*   $c(n)$ is the average path length of unsuccessful search in a BST (a normalization constant based on dataset size $n$).
*   The raw score $s$ ranges from 0 to 1 (near 1 = anomaly, small path).

**Scikit-Learn Adjustment**:
The `decision_function(x)` outputs a value that is **shifted** so that 0 represents the default decision boundary (usually 0.5 raw probability).

$$ \text{decision\_function}(x) = 0.5 - 2^{ -\frac{E(h(x))}{c(n)} } $$
*(Note: Interpretation varies slightly by version, but the sign convention is consistent below)*

**Sign Convention**:
*   **Positive Score**: Inlier (Normal). High path length.
*   **Negative Score**: Outlier (Anomaly). Short path length.
*   **Lower is "More Anomalous"**.

### 3. Threshold Interpretation
Our selected threshold is **-0.0451**.
*   Samples with score > -0.0451 are considered **Normal** (Benign).
*   Samples with score < -0.0451 are considered **Anomalous**.

This threshold cuts deeply into the negative range, effectively ignoring "mild" outliers and focusing only on the most distinct deviations (the top 1% of the benign distribution). This ensures that the Active Magnet only engages when the behavior is statistically extreme even relative to other edge cases.
