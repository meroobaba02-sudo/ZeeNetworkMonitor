"""Fetch the user's requested starter region once, before packaging."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from zee.regionmap import download,validate
import gzip,json
data=download()
(Path(__file__).resolve().parents[1]/'assets/region_map.json.gz').write_bytes(gzip.compress(json.dumps(data).encode(),mtime=0))
print('Zhob–Sambaza vector map downloaded and validated.')
