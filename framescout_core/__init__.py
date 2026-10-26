"""Shared helpers for the FrameScout app (app.py) and engine (framescout_engine.py).

The package uses only the Python standard library, so it can be imported and tested
without torch, Streamlit or any model download. It has one module per area (I15); this
file re-exports their public names, so "import framescout_core" and
"from framescout_core import <name>" work as before. Private helpers (leading
underscore) are not re-exported: import or monkeypatch them on their defining module
(e.g. framescout_core.cleanup._remove_file), where the calling code looks them up.
The same holds for a public name that another module imports, e.g. read_profiles as
used by the cleanup: patch framescout_core.cleanup.read_profiles.
"""
from .names import (AVIF_EXT, HEIF_EXT, RAW_EXT, EXT, SLUG_MAX_LENGTH, slugify, profile_slugs)
from .photos import (RAW_PARTNER_EXT, RAW_PREVIEW_MIN_EDGE, RAW_FLIP_TRANSPOSE, SKIPPED_EXTENSIONS_SHOWN,
    PhotoScan, Decoders, ALL_DECODERS, available_decoders, supported_extensions, missing_decoder, scan_photos,
    distinct_folders, output_folder_problem, missing_folders_message, folder_labels, photo_name, scan_folders,
    join_scans,
    skipped_lines, raw_preview_usable, raw_preview_transpose)
from .locks import (RunLock, lock_held)
from .references import (reference_folder, stage_reference_move, finish_reference_move,
    undo_reference_move, update_backup_references, write_new_file)
from .profiles import (create_from_example, generic_prompts, load_profiles, read_profiles,
    save_profiles)
from .models import (SearchModel, MODELS, DEFAULT_MODEL, MODEL_KEYS, model_label, missing_packages,
    model_problem)
from .signature import (CLIP_MODEL, CLIP_PRETRAINED, ENGINE_TEMPLATE, engine_id, ENGINE, MODEL_ENGINES,
    feature_signature, CACHE_FILE,
    DEFAULT_YOLO_MODEL, prepare_cache, SLIDER_NOISE_ULPS, known_signatures, classify_signatures)
from .torch_build import (TORCH_VERSION, TORCHVISION_VERSION, TORCH_INDEX, CUDA_BUILDS,
    parse_gpu_query, unsupported_gpus, cuda_build, driver_text, torch_requirements,
    installed_build_matches, installed_cuda_build, torch_index_url)
from .devices import (device_choices, cuda_hint, cuda_status, DETECTION_IMAGE_SIZE,
    detection_options, ULTRALYTICS_ENV, import_detector_class)
from .thumbnails import (FULL_IMAGE_LABEL, crop_label, thumbnail_name, ensure_thumbnail)
from .pipeline import (progress_line, progress_due, DRAFT_REDUCING_GAP, DRAFT_DECODING, draft_size,
    group_batches, store_group, prefetch)
from .run_status import (RUN_LOCK, RUN_STATUS, STATUS_FORMAT, PHASE_LABELS, FINAL_PHASES,
    StatusReporter, write_status, stopped_status, started_in_time, final_status, read_status,
    run_active, status_fraction, status_text)
from .settings import (SETTINGS_FILE, DEVICES, SETTING_RANGES, SETTING_STEPS,
    DEFAULT_REFERENCE_WEIGHT, SETTINGS_LOCK_TIMEOUT, LEGACY_PHOTO_FOLDER, default_settings, folder_lines,
    read_settings, save_settings, reconcile_settings)
from .results import (RESULTS_FILE, RESULTS_FORMAT, GALLERY_PAGE_SIZE, search_fingerprint,
    profile_fingerprints, profile_state, result_card, results_document, write_results, read_results,
    page_count, page_cards, openable_photo, open_command, reveal_command)
from .marks import (MARKS_FILE, MARKS_FORMAT, MARK_OPEN, MARK_MATCH, MARK_NO_MATCH, MARK_STATES,
    MARKS_LOCK_TIMEOUT, read_marks, save_marks, rename_marks)
from .copying import (COPY_FOLDERS_KEY, COPY_MAX_NAMES, default_copy_folder, copy_target,
    copy_photos, copy_summary_text, read_copy_folders, save_copy_folder, rename_copy_folder)
from .cleanup import (THUMBNAILS_DIR, LEGACY_THUMBNAILS_DIR, GALLERY_MARKER, CLEANUP_CATEGORIES,
    CLEANUP_DEFAULTS, NEVER_DELETED, CLEANUP_LOCK_TIMEOUT, scan_cleanup, cleanup_running, clean_up,
    auto_cleanup, size_text, count_text, cleanup_summary_text)
