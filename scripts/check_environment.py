import os, sys, platform
from pathlib import Path
print('BhashaSaathi environment check')
print('Python:',sys.version.split()[0])
print('OS:',platform.platform())
print('Working directory:',Path.cwd())
required=['fastapi','sqlalchemy','alembic','jwt','argon2','torch','transformers','faster_whisper']
for name in required:
    try:
        module=__import__(name); print('OK ',name,getattr(module,'__version__','installed'))
    except Exception as exc: print('MISS',name,exc)
