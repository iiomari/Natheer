"""Nazeer (نَظير): Saudi-aware synthetic and masked data engine."""
from nazeer.config import enforce_offline

# Set before any submodule can import transformers / huggingface_hub.
enforce_offline()

__version__ = "0.1.0"
