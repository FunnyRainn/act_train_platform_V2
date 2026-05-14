# act_train_platform Version Plan

## Current Version

`v1.0.0.0`

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
