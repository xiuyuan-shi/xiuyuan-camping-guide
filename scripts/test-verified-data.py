"""Compatibility entry for canonical-library regression checks."""
from pathlib import Path
import subprocess,sys
subprocess.run([sys.executable,str(Path(__file__).with_name('test-data.py'))],check=True)
