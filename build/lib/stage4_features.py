"""
Feature extraction utilities for threat detection.
Consolidated into sampler to maintain edge obfuscation prior to hashing.
"""
def extract_stage4_features(content: str, timestamp_str: str, last_timestamp: float = None) -> dict:
    """
    Extract scalar features for threat-focused classification.
    NO RAW CONTENT IS RETURNED.
    """
    import re
    from datetime import datetime
    
    # 1. Complexity (Entropy approximation)
    # Using simple compression ratio or unique char ratio as proxy for entropy
    if not content:
        complexity = 0.0
    else:
        unique_chars = len(set(content))
        complexity = unique_chars / len(content)
        
    # 2. Code Density
    code_blocks = len(re.findall(r'```', content)) / 2  # Approximate pairs
    code_density = min(1.0, code_blocks * 0.2) # Normalized
    
    # 3. Toxicity / threat indicators (regex flags)
    # Basic keyword checks (safe to exist in code, just regex)
    toxic_patterns = [
        r'http[s]?://',           # Links (Phishing/Spam)
        r'ignore previous',       # Injection
        r'system prompt',         # Injection
        r'kill all humans',       # Explicit violent threat phrase
    ]
    toxicity_score = 0
    for pat in toxic_patterns:
        if re.search(pat, content, re.IGNORECASE):
            toxicity_score += 1
    
    # 4. Latency (Temporal)
    # This requires state (last timestamp), handled by caller ideally, 
    # but we can calculate current-time offset if live or just return raw ts for diffing later.
    # For edge extraction, we return the timestamp float for the aggregator to diff.
    try:
        ts_float = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00')).timestamp()
    except Exception:
        ts_float = 0.0
        
    return {
        "f_complexity": round(complexity, 3),
        "f_code_density": round(code_density, 2),
        "f_toxicity": toxicity_score,
        "f_timestamp_epoch": ts_float
    }
