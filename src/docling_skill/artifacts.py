"""Artifact extraction helpers for ingestion outputs."""

from __future__ import annotations

import base64
from io import BytesIO
from typing import Any

from docling_core.types.doc import PictureItem

from .constants import IMAGE_PLACEHOLDER
from .models import ImageSidecar


def _picture_id(page_no: int | None, index: int) -> str:
    normalized_page_no = page_no if page_no is not None else 0
    return f"picture-p{normalized_page_no}-{index}"


def _encode_image_base64(picture_item: PictureItem, document: Any) -> tuple[str, str] | None:
    image = picture_item.get_image(document)
    if image is None:
        return None

    image_buffer = BytesIO()
    image.save(image_buffer, format="PNG")
    return "image/png", base64.b64encode(image_buffer.getvalue()).decode("utf-8")


def _collect_picture_sidecars(
    document: Any,
    *,
    encode_image_base64=_encode_image_base64,
    picture_id_factory=_picture_id,
) -> list[ImageSidecar]:
    pictures: list[ImageSidecar] = []
    picture_indices_by_page: dict[int, int] = {}

    for item, _level in document.iterate_items(traverse_pictures=True):
        if not isinstance(item, PictureItem):
            continue

        encoded = encode_image_base64(item, document)
        if encoded is None:
            continue

        mime_type, image_base64 = encoded
        prov = item.prov[0] if item.prov else None
        page_no = getattr(prov, "page_no", None)
        page_index = picture_indices_by_page.get(page_no or 0, 0)
        picture_indices_by_page[page_no or 0] = page_index + 1

        picture_id = picture_id_factory(page_no, page_index)
        placeholder = f"[[image:{picture_id}]]"

        pictures.append(
            {
                "id": picture_id,
                "placeholder": placeholder,
                "self_ref": getattr(item, "self_ref", None),
                "page_no": getattr(prov, "page_no", None),
                "bbox": prov.bbox.model_dump() if prov and getattr(prov, "bbox", None) else None,
                "caption_refs": [caption.cref for caption in item.captions],
                "mime_type": mime_type,
                "base64": image_base64,
            }
        )

    return pictures


def _group_pictures_by_page(
    pictures: list[ImageSidecar],
) -> dict[int, list[ImageSidecar]]:
    pictures_by_page: dict[int, list[ImageSidecar]] = {}
    for picture in pictures:
        page_no = picture.get("page_no")
        if page_no is None:
            continue
        pictures_by_page.setdefault(page_no, []).append(picture)
    return pictures_by_page


def _inject_picture_placeholders(markdown_text: str, pictures: list[ImageSidecar]) -> str:
    updated_markdown = markdown_text

    for picture in pictures:
        if IMAGE_PLACEHOLDER in updated_markdown:
            updated_markdown = updated_markdown.replace(
                IMAGE_PLACEHOLDER, picture["placeholder"], 1
            )
        else:
            updated_markdown += f"\n\n{picture['placeholder']}\n"

    return updated_markdown


def _export_structured_document(document: Any) -> dict[str, Any]:
    export_to_dict = getattr(document, "export_to_dict", None)
    if callable(export_to_dict):
        return export_to_dict()

    model_dump = getattr(document, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")

    dict_method = getattr(document, "dict", None)
    if callable(dict_method):
        return dict_method()

    raise TypeError("Docling document does not expose a supported structured export method")
