"""macOS launcher: read local .env as data, preserve runtime state, start one server."""
from pathlib import Path
import importlib.util
import os

from dotenv import load_dotenv
import uvicorn


def main():
    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / '.env', override=False)
    spec = importlib.util.spec_from_file_location('blinkspace_initialize_data', root / 'docker/initialize_data.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.initialize(root / 'seed-data', Path(os.getenv('BLINKSPACE_DATA_DIR', str(root / 'data'))))
    print('BlinkSpace: http://127.0.0.1:8765')
    uvicorn.run('blinkspace.api:app_factory', factory=True, host='127.0.0.1', port=8765, workers=1)


if __name__ == '__main__':
    main()
