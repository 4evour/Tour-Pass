"""External provider adapters."""

from .amap import AmapProvider
from .rail import Rail12306Provider

__all__ = ["AmapProvider", "Rail12306Provider"]
