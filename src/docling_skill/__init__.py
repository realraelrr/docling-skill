"""Agent-oriented Markdown and Docling JSON sidecar extraction on top of Docling."""

from .core import convert_document_to_ingestion_outputs, convert_pdf_to_sidecar_outputs

__all__ = [
    "convert_document_to_ingestion_outputs",
    "convert_pdf_to_sidecar_outputs",
]
__version__ = "0.1.0"
