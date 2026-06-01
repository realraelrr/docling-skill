"""Agent-oriented local document ingestion sidecars on top of Docling."""

from .constants import PRODUCER_VERSION
from .core import convert_document_to_ingestion_outputs, convert_pdf_to_sidecar_outputs

__all__ = [
    "convert_document_to_ingestion_outputs",
    "convert_pdf_to_sidecar_outputs",
]
__version__ = PRODUCER_VERSION
