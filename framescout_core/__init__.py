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
from .layout import (CORE_PACKAGE, SCORING_PACKAGE, REPLACED_PACKAGES, OBSOLETE_CORE_FILE, LAYOUT_MARKER,
    leftover_text, leftover_fix, mixed_versions_message, marked_script, refused_import, refuse_mixed_versions)

# First of all (I16): next to framescout_core.py of an older version, the importing app.py
# may be that older version's, which must not run against this core (unless it carries the
# marker of a version with the package, I35).
refuse_mixed_versions(__file__)

from .paths import (REQUIREMENTS_DIR, REQUIREMENTS_FILE, CONSTRAINTS_FILE, ASSETS_DIR, EXAMPLE_PROFILES_FILE,
    EVAL_PAGE_FILE, windows_path)
from .names import (AVIF_EXT, HEIF_EXT, RAW_EXT, EXT, SLUG_MAX_LENGTH, slugify, profile_slugs)
from .photos import (RAW_PARTNER_EXT, RAW_PREVIEW_MIN_EDGE, RAW_FLIP_TRANSPOSE, SKIPPED_EXTENSIONS_SHOWN,
    PhotoScan, Decoders, ALL_DECODERS, available_decoders, supported_extensions, missing_decoder, scan_photos,
    TruncatedImageError, jpeg_scans_missing, distinct_folders, output_folder_problem, missing_folders_message, folder_labels, photo_name, scan_folders,
    scan_each_folder, remembered_scans,
    join_scans, raw_fallbacks, RawFallback,
    skipped_lines, raw_preview_usable, raw_preview_transpose)
from .locks import (RunLock, lock_held)
from .references import (reference_folder, stage_reference_move, finish_reference_move,
    undo_reference_move, update_backup_references, write_new_file)
from .profiles import (PROFILES_LOCK_TIMEOUT, ProfilesChangedError, UnknownProfileError, create_from_example,
    generic_prompts, load_profiles, profiles_changed_notice, read_profiles, read_profiles_versioned, require_profile, save_profiles)
from .models import (SearchModel, MODELS, DEFAULT_MODEL, MODEL_KEYS, model_label, missing_packages,
    model_problem, results_model)
from .signature import (ENGINE_TEMPLATE, engine_id, ENGINE, MODEL_ENGINES,
    feature_signature, CACHE_FILE,
    DEFAULT_YOLO_MODEL, prepare_cache, SLIDER_NOISE_ULPS, known_signatures, classify_signatures)
from .hub import (HUB_QUIET_ENV, WEIGHTS_FILES, TOKENIZER_FILES, OFFLINE_VARIABLES, hub_cache_dir,
    hub_file_cached, model_cached, import_open_clip, hub_go_online, hub_file_error, load_with_hub_fallback)
from .cache_dirs import (CACHE_DIR, cache_folder_paths, cache_paths, default_cache_env, engine_cache_env,
    find_yolo_weights, open_clip_cache_dir, yolo_weights, XDG_DERIVED)
from .torch_build import (TORCH_VERSION, TORCHVISION_VERSION, TORCH_INDEX, CUDA_BUILDS,
    parse_gpu_query, unsupported_gpus, cuda_build, driver_text, torch_requirements,
    installed_build_matches, installed_cuda_build, torch_index_url)
from .portable_python import (PYTHON_VERSION, PYTHON_URL, PYTHON_SHA256, PRIVATE_PYTHON)
from .devices import (device_choices, cuda_hint, cuda_status, DETECTION_IMAGE_SIZE,
    detection_options, ULTRALYTICS_ENV, import_detector_class)
from .thumbnails import (FULL_IMAGE_LABEL, crop_label, thumbnail_name, ensure_thumbnail, gallery_cards,
    SKIP_LOG_LIMIT, SkippedPhotos)
from .pipeline import (progress_line, progress_due, DRAFT_REDUCING_GAP, DRAFT_DECODING, draft_size,
    group_batches, store_group, prefetch, Lazy)
from .run_status import (RUN_LOCK, RUN_STATUS, STATUS_FORMAT, PHASE_LABELS, FINAL_PHASES, NOTHING_NEW, LOADING_DETECTOR,
    StatusReporter, write_status, stopped_status, started_in_time, final_status, read_status,
    run_active, status_fraction, status_text)
from .settings import (SETTINGS_FILE, DEVICES, SETTING_RANGES, SETTING_STEPS,
    DEFAULT_REFERENCE_WEIGHT, AI_SETTINGS, SETTINGS_LOCK_TIMEOUT, LEGACY_PHOTO_FOLDER, default_settings, folder_lines,
    read_settings, save_settings, reconcile_settings, changed_from_defaults, setting_text, engine_command)
from .quick import (QUICK_DIR, QUICK_GALLERY, QUICK_QUERY_MAX, quick_profile, quick_photos, quick_scope_text,
    quick_note)
from .results import (RESULTS_FILE, RESULTS_FORMAT, GALLERY_PAGE_SIZE, search_fingerprint,
    profile_fingerprints, profile_state, result_card, results_document, publish_export,
    read_results, page_count, page_cards, openable_photo, open_command, reveal_command)
from .marks import (MARKS_FILE, MARKS_BACKUP, MARKS_FORMAT, MARK_OPEN, MARK_MATCH, MARK_NO_MATCH, MARK_STATES,
    MARKS_LOCK_TIMEOUT, marks_backup, read_marks, save_marks, rename_marks, delete_marks, remove_marks,
    restore_marks, marks_restore_offer, hide_no_match, hidden_text, MARK_COLORS, MARK_STYLE_STREAMLIT, mark_style)
from .copying import (COPY_FOLDERS_KEY, COPY_MAX_NAMES, default_copy_folder, copy_target,
    copy_photos, copy_summary_text, read_copy_folders, save_copy_folder, rename_copy_folder, forget_copy_folder)
from .exporting import (EXPORTS_DIR, EXPORT_COLUMNS, EXPORT_MARK_TEXT, EXPORT_MAX_NAMES, export_cards, export_csv,
    export_file_list, export_name, export_result_list, unlisted_paths)
from .cleanup import (THUMBNAILS_DIR, LEGACY_THUMBNAILS_DIR, GALLERY_MARKER, CLEANUP_CATEGORIES,
    CACHE_CATEGORIES, CLEANUP_DEFAULTS, NEVER_DELETED, CLEANUP_LOCK_TIMEOUT, ROOT_TIMEOUT, FOLDER_TIMEOUT, STALE_TEMP_AGE, scan_cleanup, cleanup_running, clean_up,
    auto_cleanup, project_temp_cleanup, size_text, count_text, cleanup_summary_text)
from .disk_space import (TORCH_INSTALL_SPACE, OTHER_PACKAGES_SPACE, CACHE_BYTES_PER_PHOTO, THUMBNAIL_BYTES, DETECTOR_DOWNLOAD, SPACE_RESERVE,
    SPACE_CHECK_TIMEOUT, LowSpace, analyzed_photos, app_search_needs, download_bytes, downloaded_models, eval_run_needs, search_space_bytes, search_space_needs, torch_install_needs, low_space, low_space_lines)
from .priority import (MAX_TORCH_THREADS, BELOW_NORMAL_PRIORITY_CLASS, IDLE_PRIORITY_CLASS, LOW_PRIORITY_NICE, torch_threads,
    lower_priority)
from .estimate import (RATE_WINDOW, RATE_MIN_PHOTOS, RATE_MIN_SECONDS, RATE_STALE, THROUGHPUT_KEPT, THROUGHPUT_MIN_SECONDS,
    FINISHING_STEPS, FINISHING_MIN_ITEMS, FINISHING_MIN_SECONDS, AnalysisRate, StepSpeed, duration_text, finishing_minutes, gallery_thumbnails,
    known_throughput, remaining_text, remember_finishing, remember_throughput, run_throughput, start_summary,
    stored_finishing, stored_throughput)
from .install_check import (VENV_DIR, TORCH_CHECK_TIMEOUT, TORCH_PROBE, REINSTALL,
    CheckResult, venv_python, venv_site_packages, requirement_names, installed_versions, check_program_files, check_environment, check_packages, check_torch,
    check_writable, check_models, check_disk_space, check_installation, check_lines)
from .cache_check import (CACHE_CHECK_LINES, CACHE_SIDE_FILES, cache_check_current, cache_error, cache_error_message,
    cache_read_warning, check_cache, set_cache_aside)
from .uninstall import (UNINSTALL_ITEMS, UNINSTALL_KEEP, UNINSTALL_FIRST, USER_DATA, ENVIRONMENT_PROGRAMS,
    PRIVATE_PYTHON_EXIT_CODE, UninstallItem, protected_folders, uninstall_plan, running_python, user_data,
    outside_leftovers, search_running, programs_in_use, remove_items)
from .evaluation import (SCORES_FORMAT, LABELS_FORMAT, EVAL_K, SCORE_DIGITS, collection_name_problem,
    write_document, read_document, scores_document, write_scores, read_scores, read_labels, save_labels, set_label, average_precision, build_pool,
    read_label_file, motif, record_motif, changed_motifs)
