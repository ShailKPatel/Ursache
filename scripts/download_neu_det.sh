#!/usr/bin/env bash
# Prints instructions only; downloads nothing. The dataset is fetched manually so its
# licence terms are read by a human before use.
set -euo pipefail

cat <<'TXT'
NEU surface defect database (NEU-DET): 1,800 grayscale 200x200 images of hot-rolled steel
strip, six classes (crazing, inclusion, patches, pitted_surface, rolled-in_scale, scratches),
300 images each.

1. Get the dataset from its official source (Northeastern University, K. Song and Y. Yan)
   or a mirror that states the original licence, and read the terms of use.
2. Extract it so the class folders end up under:
       data/raw/neu-det/<class_name>/*.jpg|*.bmp
3. Later phases ingest from there: images are uploaded to blob storage (B2 in prod,
   data/blobs locally) and registered in kb.images.

data/raw/ is git-ignored. Nothing in this repository redistributes the images.
TXT
