"""Package core de Sentinel-Edge."""
from core.stream import VideoStream, VideoStreamState

try:
    from core.detector import IntrusionDetector
    __all__ = ["VideoStream", "VideoStreamState", "IntrusionDetector"]
except ImportError:
    __all__ = ["VideoStream", "VideoStreamState"]
