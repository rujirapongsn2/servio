"""Carousel marker protocol for knowledge image presentations.

When an OKF knowledge query returns images, the model is instructed to end
its final reply with the exact marker ``[[carousel]]`` when the user's intent
is shopping/comparing products. The websocket layer strips the marker from
every outgoing surface (streamed partials, history, channels) and converts
the stacked ``knowledge_images`` presentation into a selectable
``knowledge_product_carousel`` rendered at the assistant message.
"""

MARKER = "[[carousel]]"


def _strip_text(text: str) -> str:
    return text.replace(MARKER, "").rstrip()


def strip_marker(content):
    """Remove the marker from an assistant message content.

    ``content`` is either a plain string or a list of content parts with
    ``{"type": "output_text", "text": ...}`` items (the SDK history shape).
    Mutates lists in place and returns ``(content, had_marker)``.
    """
    if isinstance(content, str):
        if MARKER not in content:
            return content, False
        return _strip_text(content), True
    if isinstance(content, list):
        had = False
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str) and MARKER in part["text"]:
                part["text"] = _strip_text(part["text"])
                had = True
        return content, had
    return content, False


def build_carousel_message(images, refs, summary_text, team_agent_id=None):
    """Build a knowledge_product_carousel presentation for the client.

    ``images`` is the list from a ``knowledge_images`` presentation
    (asset_id/title/source_label/image_url, in reference order). ``refs`` is
    the matching list of KnowledgeCardRef values in the same order. Returns
    ``(message_id, presentation_dict, card_refs)`` where ``card_refs`` maps
    card_id -> KnowledgeCardRef for later product inquiries.
    """
    import time
    import uuid

    from app.knowledge_image_search import KnowledgeCard, KnowledgeCarousel, SearchMatch, _unique_product_matches

    if not images or len(images) != len(refs):
        return None

    part_numbers = {}
    if team_agent_id is not None:
        matches = [SearchMatch(ref, image["title"], image["source_label"], "", 1 - index / 100)
                   for index, (image, ref) in enumerate(zip(images, refs))]
        selected = _unique_product_matches(matches, team_agent_id, 5)
        by_reference = {ref: image for image, ref in zip(images, refs)}
        images = [by_reference[match.reference] for match in selected]
        refs = [match.reference for match in selected]
        part_numbers = {match.reference: match.part_number for match in selected}

    from app.product_catalog_labels import catalog_labels
    labels = catalog_labels([image["asset_id"] for image in images], team_agent_id)
    card_refs = {}
    products = []
    for image, ref in zip(images, refs):
        card_id = uuid.uuid4().hex
        card_refs[card_id] = ref
        products.append(
            KnowledgeCard(
                id=card_id,
                asset_id=image["asset_id"],
                title=labels.get(image["asset_id"], {}).get("title", image["title"]),
                part_number=labels.get(image["asset_id"], {}).get("part_number", part_numbers.get(ref)),
                brand=labels.get(image["asset_id"], {}).get("brand"),
                source_label=image["source_label"],
                description="",
                image_url=image["image_url"],
            )
        )
    summary = (summary_text or "").strip()[:1000] or f"พบสินค้าที่ใกล้เคียง {len(products)} รายการ"
    carousel = KnowledgeCarousel(summary=summary, products=products)
    return "msg_" + uuid.uuid4().hex, carousel.model_dump(exclude_none=True), card_refs
