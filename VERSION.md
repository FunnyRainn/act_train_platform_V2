# act_train_platform Version Plan

## Current Version

`v1.2.1.6`

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

## v1.2.1.6

- Adds front-end validation for video upload and server-path import so missing product, missing file, or missing path are shown as clear customer-facing prompts instead of FastAPI 422 errors.
- Keeps the backend upload/import API unchanged; this is a low-risk page interaction fix after packaged deployment verification.

## v1.2.1.5

- Stops scanning every dataset/model JSON file at startup for path repair, avoiding slow or stuck startup when the training data directory is large.
- Keeps lightweight SQLite path repair on startup and moves dataset YAML/JSON path repair to on-demand use by training and model-package export.
- Adds a temporary-data-root smoke check covering project creation, video upload, frame extraction, annotation save, and dataset export without touching production data.
- Keeps upload, frame extraction, and dataset export behavior aligned with the pre-governance implementation while preserving portable runtime path resolution.

## v1.2.1.4

- Hides the internal base model path from the training page and uses the system default base model on the backend.
- Replaces the customer-visible worker log console with business training phases such as preparation, model loading, dataset checking, and training.
- Keeps detailed worker diagnostics in `worker.log` for operations use without showing raw logs on the customer page.
- Cleans training-related mojibake in the training page, training script, training worker, and common helper text.

## v1.2.1.3

- Fix packaged training jobs that can appear stuck before the first epoch on Windows by using in-process data loading by default for training workers.
- Capture training worker stdout/stderr into `worker.log` and surface the tail in the training task list for diagnosis.
- Prefer the packaged installation's own `data` directory for platform-owned paths, even when the old development path still exists on the same machine.
- Fix customer-visible mojibake on the training page and training-related runtime error messages.

## v1.2.1.2

- Add runtime path resolution for packaged deployments copied to a different drive or machine.
- Repair safely mappable platform-owned paths in SQLite and dataset metadata on startup.
- Make training jobs resolve migrated dataset and output directories before invoking Ultralytics.
- Update packaging guidance so deployments can live under any `act_det` directory, not a fixed drive.

## v1.2.1.1

- Fix packaged executable startup by passing the already-created FastAPI app object to Uvicorn instead of re-importing `app:app`.
- This keeps source-mode startup unchanged while allowing `act_train_platform.exe` to run correctly after PyInstaller packaging.

## v1.2.1.0

- Adds external YOLO detection dataset import on the training dataset page.
- Supports inspect-and-confirm label mapping before copying data into `data/datasets`.
- Stores imported datasets as normal dataset versions with source metadata, label mapping, image-size stats, and recommended input size.

## v1.2.0.1

- Fix training ETA display by preferring Ultralytics `results.csv` cumulative `time` and reported `epoch`.
- Fall back to wall-clock ETA only when CSV timing is unavailable.
- Show no ETA for finished, stopped, failed, zero-progress, or already-complete jobs.

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

## v1.1.0.4

Packaging release:

- Added `scripts/package_act_train_platform.ps1` for one-command PyInstaller packaging.

## v1.2.0.0

Architecture governance release with no intended behavior changes:

- Moves FastAPI construction into `web/app_factory.py` and routes into `web/routes/`.
- Splits SQLite access behind `core/repositories/` while keeping `core.store` as a compatibility facade.
- Moves dataset export, media, annotation, pre-labeling, and training implementations into domain packages under `core/`.
- Keeps old module names such as `core.dataset_ops`, `core.video_ops`, and `core.training_ops` as compatibility shims.
- Moves the annotation and dataset page implementations under page-specific frontend directories while keeping the original entry scripts as bootstraps.
- Updates architecture documentation to describe the new module responsibilities.
- The packaged application creates an empty runtime `data/` directory structure and does not bundle local videos, datasets, databases, training runs, or model packages.
- Base model files in the project root, such as `yolo11m.pt` and `yolo26n.pt`, are copied beside the packaged executable so the default training form can run after deployment.
- Added packaged training-worker support through `act_train_platform.exe --train-worker <job_id>`, so training jobs still run as child processes after the app is packaged.
- Added `docs/PACKAGING.md` with deployment commands and data migration notes.

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

## v1.0.0.6

Annotation shortcut reliability fix:

- Allows `A` / `D` frame shortcuts to work when focus remains on the frame-set or label select.
- Keeps shortcuts disabled while typing in text inputs, textareas, or editable fields.
- Uses physical key codes as the primary shortcut signal with key-value fallback.

## v1.0.0.7

Annotation shortcut event-order fix:

- Handles `A` / `D` shortcuts during the keyboard capture phase so focused select controls cannot consume the key before frame navigation runs.

## v1.0.0.8

Pre-label feedback, frame-set management, and model-folder handoff update:

- Shows visible pre-label running/completed/failed status in the annotation workspace.
- Displays confidence values on pre-label boxes in both canvas labels and the box list.
- Adds clearing for all unconfirmed pre-label boxes in the current frame set.
- Adds `Ctrl+O` as a shortcut for clearing boxes on the current frame.
- Allows custom frame-set names during frame extraction and supports explicit overwrite for duplicate names.
- Adds frame-set deletion, including extracted frame images and related annotations/tracks.
- Hides video assets, product videos, and frame sets whose backing files or directories are missing.
- Adds a model repository action to open the deployable model directory in Windows Explorer.

## v1.0.0.9

Dataset export merge and validation fix:

- Prevents dataset export when neither frame sets nor historical datasets are selected.
- Actually merges selected historical dataset image/label files into newly exported datasets.
- Remaps historical label class ids by label code to avoid class-index mismatch.
- Validates historical dataset directory structure and label compatibility before export.
- Improves dataset list summaries with current-frame counts, historical-mix counts, skipped-frame counts, and split totals.

## v1.0.0.10

Annotation save race and pre-label count clarification:

- Saves annotation snapshots against the exact frame that triggered the save, instead of reading the current frame at execution time.
- Flushes pending annotation saves before frame switching, pre-labeling, interpolation, and bulk pre-label clearing.
- Adds backend validation so a frame can only be overwritten through its own frame set.
- Clarifies that pre-label counts are whole-frame-set totals while the canvas shows only the current frame.
- Shows current-frame box counts in the frame information line.

## v1.0.0.11

Pre-label confirmation and export clarity:

- Rewrites the annotation workspace script with clean Chinese text after legacy mojibake broke several JS strings.
- Keeps autosave bound to the frame snapshot that triggered the save, preventing quick frame switching from overwriting the wrong frame.
- Shows pre-label totals as whole-frame-set counts and current-frame counts separately.
- Adds explicit single-box confirmation and current-frame-set bulk pre-label confirmation.
- Makes dataset export summaries show manual boxes, confirmed pre-label boxes, and skipped unconfirmed pre-label boxes.

## v1.0.0.12

Annotation frame-load and pre-label count follow-up:

- Adds a frame image load token so stale image-load callbacks cannot overwrite the currently selected frame's annotation boxes.
- Keeps pre-label completion text based on database totals while also showing the current frame's pre-label count after reload.
- Preserves the confirmed-only dataset export rule for pre-label boxes.

## v1.1.0.0

Focus-region training dataset release:

- Adds product/workstation focus-region management in the annotation workspace.
- Lets annotators draw, name, confirm, lock, edit, and delete non-overlapping focus regions.
- Dims content outside configured focus regions and blocks new or edited boxes outside the valid focus area.
- Marks legacy boxes outside focus regions as invalid for focus-region export without deleting historical annotations.
- Reworks dataset export so users can create full-image datasets, focus-region cropped datasets, or history-only merged datasets.
- Generates one independent dataset version for each selected focus region, with per-region historical dataset mixing.
- Crops focus-region images and translates bbox labels into the cropped coordinate system.
- Records `image_scope`, focus-region metadata, source size, label codes, and history sources in dataset metadata.
- Writes focus-region metadata into exported model manifests so inference can crop the same view before running the model.

## v1.1.0.1

Focus-region editor stability fix:

- Fixes focus-region drawing coordinate drift by keeping image display, canvas, and normalized coordinates in sync.
- Lets users edit an existing focus region by dragging or resizing it like a normal annotation box.
- Adds cancel editing for focus regions so changes are not saved until explicitly confirmed.
- Keeps validation for minimum size, bounds, and non-overlap before saving.
- Rewrites the annotation and dataset export pages with clean Chinese text after legacy mojibake affected customer-facing labels.

## v1.1.0.2

Focus-region drawing state fix:

- Separates pixel drawing state from normalized focus-region draft state so a completed region no longer stretches toward the lower-right corner when the mouse moves.
- Keeps existing focus-region editing behavior: edit from the list, drag or resize, cancel, then confirm and lock.
- Removes the canvas full-container sizing conflict so pointer coordinates stay aligned with the displayed frame.

## v1.1.0.3

Input-size automation for focus-region datasets:

- Records exported dataset image-size statistics, including average/max long edge and recommended input size.
- Recommends smaller training input sizes for focus-region cropped datasets while keeping a minimum of 320 and 32-pixel alignment.
- Lets training jobs use the dataset recommended input size by default when the operator leaves the input-size field blank.
- Writes `recommended_imgsz` and `trained_imgsz` into exported model manifests so `act_server` can infer with the same scale used during training.
