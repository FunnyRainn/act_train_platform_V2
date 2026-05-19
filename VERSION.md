# act_train_platform Version Plan

## Current Version

`v1.0.0.5`

## Repository

`https://github.com/FunnyRainn/act_train_platform.git`

## Project Role

`act_train_platform` is the model-production platform for the action detection system.

It is responsible for:

- Managing A/B/C label definitions.
- Importing production videos.
- Extracting frames for annotation.
- Providing a browser-based bbox annotation workspace.
- Supporting keyframes, tracks, and linear interpolation.
- Running optional model pre-labeling.
- Exporting immutable YOLO dataset versions.
- Starting YOLO training jobs.
- Exporting model packages for manual handoff to `act_server`.

It is not responsible for production real-time inference, SOP alarm judgement, camera session orchestration, AOI runtime rule execution, desktop UI, MES/PLC integration, or hardware reset.

## Environment Rule

The first version uses the existing `train_act_det_yolo` training conda environment. This avoids reinstalling GPU Torch, Ultralytics, OpenCV, and CUDA-related dependencies.

Do not share the `act_web` or `act_server` runtime environment for training work.

## Version Rule

Versions use:

`v<major>.<feature>.<fix>.<build>`

- `major`: responsibility boundary or storage architecture changes.
- `feature`: new annotation, dataset, training, or model-package capability.
- `fix`: behavior fixes.
- `build`: packaging, documentation, or non-behavioral release iteration.

This project versions independently from `act_web`, `act_server`, `act_app`, and `train_act_det_yolo`.

## v1.0.0.0 Scope

The first stable baseline establishes a customer-facing annotation and training platform:

- FastAPI + server-rendered web pages.
- SQLite metadata storage.
- File-directory storage for videos, frames, datasets, training runs, and model packages.
- Global A/B/C label dictionary.
- Project and video management.
- Frame extraction from uploaded or server-imported videos.
- Bbox annotation workspace with keyframe and interpolation support.
- Optional model pre-labeling with manual confirmation.
- YOLO dataset export.
- YOLO training job creation.
- Standard model package export.

## Future Direction

Future versions should focus on:

- Better annotation ergonomics.
- Multi-user review and approval.
- Segmentation annotation.
- Active learning / sampling.
- Multiple model deployment profiles.
- Network-based model distribution to inference hosts.
- Training queue isolation and GPU resource scheduling.

## v1.0.0.1

Customer usability upgrade:

- Renames customer-facing training project wording to product-oriented configuration.
- Adds global asset library flow and copies selected video assets into product data directories.
- Replaces Ctrl-based label multi-select with clickable A/B/C label cards.
- Adds unified help registry for key concepts.
- Improves annotation workspace with selectable, draggable, resizable boxes and autosave.
- Rewords customer UI to avoid exposing concrete model framework names.
- Runs training in a child process so progress, stop, and partial model files can be handled.
- Adds GPU status, progress, ETA, and training-curve data sources.
- Exports model directories with `model_manifest.json` for whole-folder handoff to `act_server`.

## v1.0.0.2

Customer usability and model repository cleanup:

- Keeps selected product, dataset, and task fields stable while the training page auto-refreshes.
- Adds visible chart legends and help text for training curves.
- Keeps help text in the central help registry and fixes the tracking-object help button layout.
- Automatically creates a deployable model directory when a finished or stopped training job has `best.pt` or `last.pt`.
- Changes the model repository into a read-only repository view instead of a manual model-directory generation step.
- Improves the overview page with clearer workflow entry cards.

## v1.0.0.3

Customer-facing wording and navigation cleanup:

- Adds active state to the left navigation so users can see the current page.
- Adds dark/light theme switching and aligns colors more closely with `act_web`.
- Renames the customer-visible `SOP 名称` field to `流程说明`; the underlying database field remains `sop_name` for compatibility.
- Clarifies that training product flow text is only traceability metadata and does not participate in SOP judgement.
- Keeps help buttons inline with field labels, including the target-label help button.

## v1.0.0.4

Dataset export and pre-labeling convenience update:

- Adds an explicit annotated-frame-only dataset export entry on the training dataset page.
- Records dataset export mode in the dataset summary for traceability.
- Adds a configurable pre-label confidence threshold in the annotation workspace.
- Validates pre-label confidence on both the page and backend.

## v1.0.0.5

Annotation workspace shortcut update:

- Adds `A` / `D` keyboard shortcuts for previous-frame and next-frame navigation.
- Keeps shortcuts disabled while typing in inputs, selects, textareas, or editable fields.
