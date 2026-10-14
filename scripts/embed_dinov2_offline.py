"""Offline DINOv2 image embeddings (stub).

Plan: run on a workstation or free notebook GPU, never on the server. Load DINOv2 ViT-B/14
(768-d CLS embedding), embed every image in kb.images, and upsert the vectors into the
`dino` named vector of the `defect_images` Qdrant collection, keyed by the kb.images UUID.
The server never loads model weights; it only queries the stored vectors.

Not implemented in Phase 1: no weights are downloaded and no ML dependency is installed.
"""

import sys


def main() -> int:
    print("embed_dinov2_offline: not implemented yet (Phase 1 scaffold).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
