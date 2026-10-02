# Lets pytest import main.py without opening a window or a sound device,
# and adds the project folder to sys.path so tests can `import main`.
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
