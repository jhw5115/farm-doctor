# AI Hub orchard dataset converter

This package recursively inspects `data/images` and `data/labels`, writes
auditable CSV/Markdown reports, and can produce YOLO Classification or
Detection datasets under a separate output directory. It never edits the
source images or JSON files. The existing FastAPI, React, database, and Docker
configuration are not part of this tool.

## Install and inspect

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r scripts\dataset_converter\requirements.txt
.\.venv\Scripts\python.exe -m scripts.dataset_converter.main inspect --input data
.\.venv\Scripts\python.exe -m scripts.dataset_converter.main validate --input data
```

Reports are written to `reports/dataset` by default:

- `dataset_analysis.md`
- `class_mapping_report.md`
- `class_distribution.csv`
- `image_label_matching.csv`
- `invalid_annotations.csv`
- `duplicate_images.csv`
- `data_split_report.csv`
- `conversion_summary.md`
- `annotation_format_review.md`

The matching report records the image/JSON paths, code fields, hash, class
candidate, and capture-group candidate. Ambiguous basename matches are never
resolved by picking an arbitrary file. Image integrity is checked by decoding
the image, its raw dimensions are compared with JSON metadata, and SHA-256
plus difference-hash candidates are reported. Group IDs derived from filenames
are only hypotheses until the source's tree/orchard/session semantics are
verified.

`description.type: null` is allowed. For classification, the complete scene is
copied to the class directory; JSON points are not treated as lesion boxes.
Optional crop classification is a separate output dataset and reuses the
source image's split. It requires the same verified bbox-semantic approval as
Detection. Risk, area, growth stage, type, source paths, and image
hashes are preserved in `metadata.csv`.

## Approval gates

`config/dataset_mapping.yaml` uses the user-approved local JSON mapping. The
original user-provided table is retained in `config/official_disease_codebook.csv`
for reference; it conflicts with the local apple disease values and is not used
to label this dataset. The active mapping is recorded in
`config/local_disease_mapping.csv`.

The source `disease` code is interpreted together with `crop`; it is not itself
the final YOLO class ID. Unique target IDs are:

```text
(crop=1,disease=0) -> 0 pear_healthy
(crop=1,disease=1) -> 1 pear_scab
(crop=1,disease=2) -> 2 pear_fire_blight
(crop=2,disease=0) -> 3 apple_healthy
(crop=2,disease=3) -> 4 apple_brown_spot
(crop=2,disease=4) -> 5 apple_fire_blight
(crop=2,disease=5) -> 6 apple_valsa_canker
(crop=2,disease=6) -> 7 apple_alternaria_leaf_spot
(crop=2,disease=7) -> 8 apple_anthracnose
```

The user approved this local mapping and the filename-derived grouping policy.
Groups combine filename capture prefixes, exact SHA-256 duplicates, and
near-duplicate candidates (the configured difference-hash threshold), so those
images stay in one split. This is a leakage-reduction estimate, not verified
orchard/tree/session identity; residual leakage risk remains. With seed 42, the
splitter reports actual ratios when group boundaries prevent the requested
70/20/10 proportions. It never fabricates examples for a rare class.

Detection additionally requires `detection.bbox_semantics_verified: true`
and a review note, after confirming that points identify the intended
subject/object. The boxes are exported as subject/object locations, never
called lesion locations. Invalid boxes block Detection export; they are
reported and are not clipped or silently repaired.

The user-provided annotation schema defines `annotations.points` as the bbox
of the notable object (`xtl`, `ytl`, `xbr`, `ybr`). This is sufficient for the
approved object-location export below, but does not establish lesion-level
localization. Detection classes use the approved local `crop+disease` mapping.

## Convert and package for Colab

```powershell
.\.venv\Scripts\python.exe -m scripts.dataset_converter.main convert --input data --output data\processed --task classification --dry-run
.\.venv\Scripts\python.exe -m scripts.dataset_converter.main convert --input data --output data\processed --task classification --zip
.\.venv\Scripts\python.exe -m scripts.dataset_converter.main convert --input data --output data\processed --task detection --zip
```

The first conversion command is a dry run: it prints sample/split counts and
updates the reports but creates no dataset files. Classification can be
generated with the approved local mapping and split settings. Detection
uses subject/object boxes according to the user-provided annotation schema;
it does not represent lesion locations. If output directories already exist,
the tool refuses to overwrite them unless `--overwrite` is explicitly supplied.

Existing output directories are never overwritten unless `--overwrite` is
explicitly supplied. When replacement is approved, the existing directory or
ZIP is retained as a timestamped backup. The output `classification.zip` (and
optional `classification_crops.zip`) has `train/<class>`, `val/<class>`, and
`test/<class>` directories for Ultralytics Classification. `detection.zip`
contains `images/{train,val,test}`, `labels/{train,val,test}`, and a checked
`data.yaml`.

Colab examples and integrity checks are included in each generated dataset's
README. This utility prepares data only; it does not install model weights or
start YOLO training.
