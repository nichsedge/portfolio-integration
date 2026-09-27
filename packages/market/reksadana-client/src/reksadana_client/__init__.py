"""Indonesian Mutual Funds (Reksa Dana) Client and Screener."""

from .client import BibitReksadanaClient
from .models import FundProduct

__version__ = "0.1.0"
__all__ = ["BibitReksadanaClient", "FundProduct"]
