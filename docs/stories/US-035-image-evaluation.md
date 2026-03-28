# US-035 — Image / Multimodal Evaluation

**Associated Eva persona:** [Alex — AI Engineer](../personas.md)
**Shared base persona:** [Solo Developer](../../../../../.docs/personas/individuals/solo-developer.md)

## Story

As Alex, I want to evaluate image generation and image-grounded responses so that visual output
quality is verifiable alongside text quality.

## Acceptance Criteria

- Test cases can include `image_url` in metadata.
- `text_to_image` rates how well a generated image matches the text prompt.
- `image_editing` rates compliance with edit instructions applied to an image.
- `image_coherence` rates semantic alignment between image content and accompanying text.
- `image_helpfulness` rates whether the image adds useful information relative to the query.
- `image_reference` rates accuracy of text descriptions about an image.
- All image evaluators return a fallback `Score(0.5)` when no `image_url` is provided.
- Image evaluators require a vision-capable judge model; an error is raised if the configured
  judge does not support vision.

## Related Plan

- [Metrics Expansion Plan](../plans/2026-03-28-observability-parity-plan.md)
