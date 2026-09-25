"""Package core de Sentinel-Edge."""
try:
    from core.stream import VideoStream, VideoStreamState
except ImportError:
    VideoStream, VideoStreamState = None, None

try:
    from core.detector import IntrusionDetector
except ImportError:
    IntrusionDetector = None

try:
    from core.notifier import TelegramNotifier
except ImportError:
    TelegramNotifier = None

try:
    from core.database import SentinelDatabase
except ImportError:
    SentinelDatabase = None

__all__ = [
    "VideoStream",
    "VideoStreamState",
    "IntrusionDetector",
    "TelegramNotifier",
    "SentinelDatabase",
]
