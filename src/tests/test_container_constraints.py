import sys
from pathlib import Path
import tempfile
import subprocess
import pytest

# Paths
SRC_DIR = Path(__file__).resolve().parent.parent
SAMPLER = SRC_DIR / "calamum_sampler.py"

def test_sampler_respects_output_flag():
    """
    Verify that the sampler writes ONLY to the specified output file
    and creates no side effects in the current directory.
    This simulates the read-only rootfs constraint.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        output_path = Path(temp_dir) / "test_telemetry.jsonl"
        
        # Run the sampler with explicit output
        result = subprocess.run(
            [sys.executable, str(SAMPLER), "--output", str(output_path)],
            capture_output=True,
            text=True,
            cwd=temp_dir # Run FROM the temp dir
        )
        
        assert result.returncode == 0, f"Sampler failed: {result.stderr}"
        assert output_path.exists(), "Output file was not created"
        
        # Verify content
        with open(output_path, "r") as f:
            lines = f.readlines()
            assert len(lines) == 50, "Expected 50 samples"
            
        # Verify NO other files created in CWD (which mimics read-only root)
        # The temp_dir should contain ONLY the output file (if we directed it there) 
        # or nothing else if we put output elsewhere.
        # Ideally, we want to ensure it didn't drop a 'logs' folder or __pycache__ wherever it ran.
        
        # Note: python might create __pycache__ if imported, but we ran as script.
        # Let's check for stray files.
        found_files = list(Path(temp_dir).iterdir())
        # We expect only the output file.
        assert len(found_files) == 1, f"Found unexpected files: {found_files}"
        assert found_files[0] == output_path

if __name__ == "__main__":
    # Manually run if executed directly
    try:
        test_sampler_respects_output_flag()
        print("[PASS] test_sampler_respects_output_flag")
    except AssertionError as e:
        print(f"[FAIL] {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
