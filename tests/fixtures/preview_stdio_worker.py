"""Tiny deterministic worker; stdin must be EOF, never launcher IPC."""
import json
import sys
from pathlib import Path
from PIL import Image

request=Path(sys.argv[1]);job=json.loads(request.read_text())
assert sys.stdin.read()==''
if job.get('operation')=='discover_stock':
    (request.parent/'discovery.json').write_text(json.dumps({'items':[],'errors':[],'category':job['category']}))
else:
    Image.new('RGB',(512,320),'green').save(request.parent/'preview.png')
