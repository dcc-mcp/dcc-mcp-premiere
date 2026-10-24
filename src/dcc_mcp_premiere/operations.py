"""Bounded Premiere operations built on the typed adobepy facade."""

from __future__ import annotations

import hashlib
import math
import os
import re
from collections import deque
from pathlib import Path
from typing import Any, Optional, Sequence

from adobe.premiere import Premiere

MAX_TEXT = 512
MAX_COMMENT = 4096
MAX_MEDIA_FILES = 100
MAX_LIST_RESULTS = 1000
MAX_SCAN_ITEMS = 10_000
MAX_TRACKS = 128
MAX_CLIPS = 2000
MAX_FILE_BYTES = 64 * 1024 * 1024 * 1024
MAX_TOTAL_IMPORT_BYTES = 256 * 1024 * 1024 * 1024
HASH_CHUNK_BYTES = 1024 * 1024
FRAME_EXTENSIONS = {".jpeg", ".jpg", ".png", ".tif", ".tiff"}
SAFE_EXPORT_EXTENSION = re.compile(r"^\.[a-z0-9]{1,10}$")


class PremiereOperationError(ValueError):
    """An expected, user-correctable Premiere operation error."""


def _app(app_factory=Premiere):
    return app_factory()


def _project(app: Any) -> Any:
    project = app.project
    if project is None:
        raise PremiereOperationError("Premiere has no active project")
    return project


def _text(value: Any, field: str, maximum: int = MAX_TEXT) -> str:
    if not isinstance(value, str):
        raise PremiereOperationError(f"{field} must be a string")
    clean = value.strip()
    if not clean:
        raise PremiereOperationError(f"{field} must not be empty")
    if len(clean) > maximum:
        raise PremiereOperationError(f"{field} must be at most {maximum} characters")
    if any(ord(character) < 32 and character not in "\t\n" for character in clean):
        raise PremiereOperationError(f"{field} contains unsupported control characters")
    return clean


def _integer(value: Any, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PremiereOperationError(f"{field} must be an integer")
    if value < minimum or value > maximum:
        raise PremiereOperationError(f"{field} must be between {minimum} and {maximum}")
    return value


def _number(value: Any, field: str, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PremiereOperationError(f"{field} must be a number")
    result = float(value)
    if not math.isfinite(result) or result < minimum:
        raise PremiereOperationError(f"{field} must be finite and at least {minimum}")
    return result


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in list(value.items())[:100]}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in list(value)[:100]]
    return str(value)


def _project_data(project: Any) -> dict[str, Any]:
    return {
        "id": _json_value(project.id),
        "guid": project.guid,
        "name": project.name,
        "path": project.path,
        "item_count": int(project.item_count),
    }


def _sequence_data(sequence: Any) -> dict[str, Any]:
    return {
        "id": _json_value(sequence.id),
        "sequence_id": _json_value(sequence.sequence_id),
        "name": sequence.name,
        "duration": _json_value(sequence.duration),
        "timebase": _json_value(sequence.timebase),
        "typename": sequence.typename,
    }


def _track_data(track: Any, *, include_clips: bool, clip_limit: int) -> dict[str, Any]:
    data = {
        "id": _json_value(track.id),
        "name": track.name,
        "index": track.index,
        "media_type": track.media_type,
        "locked": track.is_locked,
        "muted": track.is_muted,
        "targeted": track.is_targeted,
        "typename": track.typename,
    }
    if include_clips:
        clips = list(track.clips)
        data.update(
            clips=[_clip_data(clip) for clip in clips[:clip_limit]],
            clip_count=len(clips),
            clips_truncated=len(clips) > clip_limit,
        )
    return data


def _clip_data(clip: Any) -> dict[str, Any]:
    return {
        "id": _json_value(clip.id),
        "name": clip.name,
        "project_item_id": _json_value(clip.project_item_id),
        "media_path": clip.media_path,
        "start": _json_value(clip.start),
        "end": _json_value(clip.end),
        "in_point": _json_value(clip.in_point),
        "out_point": _json_value(clip.out_point),
        "duration": _json_value(clip.duration),
        "enabled": clip.is_enabled,
        "selected": clip.is_selected,
        "typename": clip.typename,
    }


def _marker_data(marker: Any) -> dict[str, Any]:
    return {
        "id": _json_value(marker.id),
        "name": marker.name,
        "comments": marker.comments,
        "start": _json_value(marker.start),
        "end": _json_value(marker.end),
        "duration": _json_value(marker.duration),
        "marker_type": marker.marker_type,
        "typename": marker.typename,
    }


def _item_data(item: Any, *, depth: Optional[int] = None) -> dict[str, Any]:
    data = {
        "id": _json_value(item.id),
        "name": item.name,
        "item_type": item.item_type,
        "path": item.path,
        "media_path": item.media_path,
        "tree_path": item.tree_path,
        "parent_id": _json_value(item.parent_id),
        "child_count": int(item.child_count),
        "is_bin": bool(item.is_bin),
        "is_clip": bool(item.is_clip),
        "is_sequence": bool(item.is_sequence),
        "can_proxy": item.can_proxy,
        "has_proxy": item.has_proxy,
        "offline": item.is_offline,
        "typename": item.typename,
    }
    if depth is not None:
        data["depth"] = depth
    return data


def _job_data(job: Any) -> dict[str, Any]:
    return {
        "id": _json_value(job.id),
        "job_id": _json_value(job.job_id),
        "status": job.status,
        "output_path": job.output_path,
        "preset_path": job.preset_path,
        "source_id": _json_value(job.source_id),
        "source_name": job.source_name,
        "export_type": job.export_type,
        "remove_on_completion": job.remove_on_completion,
        "started": job.started,
        "typename": job.typename,
    }


def _sequence(project: Any, key: Any = None) -> Any:
    sequences = list(project.sequences)
    if key is None:
        active = project.active_sequence
        if active is None:
            raise PremiereOperationError("Premiere has no active sequence")
        return active
    matches = [
        sequence
        for sequence in sequences
        if str(key)
        in {
            str(sequence.id),
            str(sequence.sequence_id),
            str(sequence.name),
        }
    ]
    if not matches:
        raise PremiereOperationError(f"Sequence not found: {key}")
    if len(matches) > 1:
        raise PremiereOperationError(f"Sequence key is ambiguous: {key}")
    return matches[0]


def _walk_items(root: Any, scan_limit: int) -> tuple[list[tuple[Any, int]], bool]:
    queue = deque((child, 0) for child in root.children)
    values = []
    seen = set()
    while queue and len(values) < scan_limit:
        item, depth = queue.popleft()
        identity = str(item.id or item.tree_path or item.media_path or item.name)
        if identity in seen:
            continue
        seen.add(identity)
        values.append((item, depth))
        if item.is_bin and depth < 32:
            queue.extend((child, depth + 1) for child in item.children)
    return values, bool(queue)


def _project_item(project: Any, key: Any, *, require_bin: bool = False) -> Any:
    root = project.root_item
    if root is None:
        raise PremiereOperationError("Premiere project has no root item")
    values, truncated = _walk_items(root, MAX_SCAN_ITEMS)
    candidates = [root, *(item for item, _depth in values)]
    matches = [
        item
        for item in candidates
        if str(key)
        in {
            str(item.id),
            str(item.name),
            str(item.tree_path),
            str(item.media_path),
        }
    ]
    if not matches:
        suffix = " within the bounded scan" if truncated else ""
        raise PremiereOperationError(f"Project item not found{suffix}: {key}")
    exact_identity = [
        item
        for item in matches
        if str(key) in {str(item.id), str(item.tree_path), str(item.media_path)}
    ]
    if exact_identity:
        matches = exact_identity
    if len(matches) > 1:
        raise PremiereOperationError(f"Project item key is ambiguous: {key}")
    item = matches[0]
    if require_bin and not item.is_bin:
        raise PremiereOperationError(f"Project item is not a bin: {key}")
    return item


def _roots(variable: str) -> list[Path]:
    values = [value.strip() for value in os.getenv(variable, "").split(os.pathsep) if value.strip()]
    if not values:
        values = [str(Path.home())]
    roots = []
    for value in values:
        root = Path(value).expanduser()
        if not root.is_absolute():
            raise PremiereOperationError(f"{variable} must contain only absolute paths")
        roots.append(root.resolve(strict=False))
    return roots


def _allowed_path(
    value: str,
    *,
    variable: str,
    field: str,
    must_exist: bool,
    extensions: Optional[set[str]] = None,
) -> Path:
    path = Path(_text(value, field, 4096)).expanduser()
    if not path.is_absolute():
        raise PremiereOperationError(f"{field} must be absolute")
    path = path.resolve(strict=False)
    if not any(path == root or root in path.parents for root in _roots(variable)):
        raise PremiereOperationError(f"{field} is outside {variable}")
    if extensions is not None and path.suffix.lower() not in extensions:
        raise PremiereOperationError(f"{field} must use one of: {', '.join(sorted(extensions))}")
    if must_exist and not path.is_file():
        raise PremiereOperationError(f"{field} does not exist: {path.name}")
    return path


def _prepare_output(
    value: str,
    *,
    extensions: Optional[set[str]],
    overwrite: bool,
    create_parents: bool,
) -> Path:
    if not isinstance(overwrite, bool) or not isinstance(create_parents, bool):
        raise PremiereOperationError("overwrite and create_parents must be booleans")
    path = _allowed_path(
        value,
        variable="DCC_MCP_PREMIERE_ALLOWED_OUTPUT_ROOTS",
        field="output_path",
        must_exist=False,
        extensions=extensions,
    )
    if path.exists() and not overwrite:
        raise PremiereOperationError("output already exists; set overwrite=true to replace it")
    if path.exists() and not path.is_file():
        raise PremiereOperationError("output path exists but is not a file")
    if not path.parent.exists():
        if not create_parents:
            raise PremiereOperationError("output parent directory does not exist")
        path.parent.mkdir(parents=True, exist_ok=True)
    if not path.parent.is_dir():
        raise PremiereOperationError("output parent is not a directory")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _file_evidence(path: Path) -> dict[str, Any]:
    size = path.stat().st_size
    if size <= 0:
        raise RuntimeError("Premiere created an empty output file")
    return {
        "path": str(path),
        "bytes": size,
        "sha256": _sha256(path),
    }


def _file_state(path: Path) -> tuple[int, int] | None:
    if not path.is_file():
        return None
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def _verified_changed_output(path: Path, previous: tuple[int, int] | None) -> dict[str, Any]:
    current = _file_state(path)
    if current is None:
        raise RuntimeError("Premiere reported success but the output file was not created")
    if previous is not None and current == previous:
        raise RuntimeError("Premiere reported success but the existing output file did not change")
    return _file_evidence(path)


def get_status(*, app_factory=Premiere) -> dict[str, Any]:
    app = _app(app_factory)
    project = app.project
    active = app.active_sequence
    encoder = app.encoder
    return {
        "version": str(app.version),
        "bridge": "adobepy-uxp",
        "project": _project_data(project) if project is not None else None,
        "active_sequence": _sequence_data(active) if active is not None else None,
        "sequence_count": len(project.sequences) if project is not None else 0,
        "ame_installed": encoder.is_ame_installed,
    }


def inspect_project(*, app_factory=Premiere) -> dict[str, Any]:
    app = _app(app_factory)
    project = _project(app)
    active = project.active_sequence
    all_selected = list(project.selected_items)
    selected = all_selected[:MAX_LIST_RESULTS]
    return {
        "project": _project_data(project),
        "active_sequence": _sequence_data(active) if active is not None else None,
        "selected_items": [_item_data(item) for item in selected],
        "selected_count": len(all_selected),
        "selected_truncated": len(all_selected) > MAX_LIST_RESULTS,
    }


def list_sequences(*, offset: int = 0, limit: int = 200, app_factory=Premiere) -> dict[str, Any]:
    offset = _integer(offset, "offset", 0, 1_000_000)
    limit = _integer(limit, "limit", 1, MAX_LIST_RESULTS)
    sequences = list(_project(_app(app_factory)).sequences)
    page = sequences[offset : offset + limit]
    return {
        "sequences": [_sequence_data(sequence) for sequence in page],
        "total": len(sequences),
        "offset": offset,
        "limit": limit,
        "truncated": offset + len(page) < len(sequences),
    }


def inspect_sequence(
    *,
    sequence: Any = None,
    include_clips: bool = True,
    clip_limit: int = 500,
    app_factory=Premiere,
) -> dict[str, Any]:
    if not isinstance(include_clips, bool):
        raise PremiereOperationError("include_clips must be a boolean")
    clip_limit = _integer(clip_limit, "clip_limit", 1, MAX_CLIPS)
    value = _sequence(_project(_app(app_factory)), sequence)
    all_video = list(value.video_tracks)
    all_audio = list(value.audio_tracks)
    all_markers = list(value.markers)
    video = all_video[:MAX_TRACKS]
    audio = all_audio[:MAX_TRACKS]
    markers = all_markers[:MAX_LIST_RESULTS]
    return {
        "sequence": _sequence_data(value),
        "video_tracks": [
            _track_data(track, include_clips=include_clips, clip_limit=clip_limit)
            for track in video
        ],
        "audio_tracks": [
            _track_data(track, include_clips=include_clips, clip_limit=clip_limit)
            for track in audio
        ],
        "markers": [_marker_data(marker) for marker in markers],
        "video_track_count": len(all_video),
        "video_tracks_truncated": len(all_video) > MAX_TRACKS,
        "audio_track_count": len(all_audio),
        "audio_tracks_truncated": len(all_audio) > MAX_TRACKS,
        "marker_count": len(all_markers),
        "markers_truncated": len(all_markers) > MAX_LIST_RESULTS,
    }


def list_project_items(
    *,
    query: Optional[str] = None,
    item_type: Optional[str] = None,
    offset: int = 0,
    limit: int = 200,
    scan_limit: int = 5000,
    app_factory=Premiere,
) -> dict[str, Any]:
    clean_query = _text(query, "query", 256).casefold() if query is not None else None
    clean_type = _text(item_type, "item_type", 64).casefold() if item_type is not None else None
    offset = _integer(offset, "offset", 0, 1_000_000)
    limit = _integer(limit, "limit", 1, MAX_LIST_RESULTS)
    scan_limit = _integer(scan_limit, "scan_limit", 1, MAX_SCAN_ITEMS)
    root = _project(_app(app_factory)).root_item
    if root is None:
        raise PremiereOperationError("Premiere project has no root item")
    walked, scan_truncated = _walk_items(root, scan_limit)
    filtered = []
    for item, depth in walked:
        if clean_query is not None and clean_query not in str(item.name or "").casefold():
            continue
        if clean_type is not None and clean_type != str(item.item_type or "").casefold():
            continue
        filtered.append((item, depth))
    page = filtered[offset : offset + limit]
    return {
        "items": [_item_data(item, depth=depth) for item, depth in page],
        "total_matches": len(filtered),
        "scanned": len(walked),
        "scan_truncated": scan_truncated,
        "page_truncated": offset + len(page) < len(filtered),
        "offset": offset,
        "limit": limit,
    }


def list_selected_clips(*, sequence: Any = None, app_factory=Premiere) -> dict[str, Any]:
    value = _sequence(_project(_app(app_factory)), sequence)
    clips = list(value.selected_clips)
    return {
        "sequence": _sequence_data(value),
        "clips": [_clip_data(clip) for clip in clips[:MAX_LIST_RESULTS]],
        "clip_count": len(clips),
        "truncated": len(clips) > MAX_LIST_RESULTS,
    }


def create_bin(
    *, name: str, parent: Any = None, make_unique: bool = True, app_factory=Premiere
) -> dict[str, Any]:
    if not isinstance(make_unique, bool):
        raise PremiereOperationError("make_unique must be a boolean")
    project = _project(_app(app_factory))
    parent_item = (
        project.root_item if parent is None else _project_item(project, parent, require_bin=True)
    )
    if parent_item is None:
        raise PremiereOperationError("Premiere project has no root bin")
    created = parent_item.create_bin(
        _text(name, "name", 256),
        make_unique=make_unique,
        command_name="DCC-MCP create bin",
    )
    return {"bin": _item_data(created), "created": True}


def import_media(
    *,
    paths: Sequence[str],
    target_bin: Any = None,
    as_numbered_stills: bool = False,
    app_factory=Premiere,
) -> dict[str, Any]:
    if not isinstance(paths, list) or not paths:
        raise PremiereOperationError("paths must be a non-empty array")
    if len(paths) > MAX_MEDIA_FILES:
        raise PremiereOperationError(f"paths is limited to {MAX_MEDIA_FILES} files")
    if not isinstance(as_numbered_stills, bool):
        raise PremiereOperationError("as_numbered_stills must be a boolean")
    resolved = [
        _allowed_path(
            path,
            variable="DCC_MCP_PREMIERE_ALLOWED_INPUT_ROOTS",
            field="input path",
            must_exist=True,
        )
        for path in paths
    ]
    total_bytes = 0
    for path in resolved:
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            raise PremiereOperationError(f"input file exceeds 64 GiB: {path.name}")
        total_bytes += size
    if total_bytes > MAX_TOTAL_IMPORT_BYTES:
        raise PremiereOperationError("combined media input exceeds 256 GiB")
    project = _project(_app(app_factory))
    bin_item = (
        project.root_item
        if target_bin is None
        else _project_item(project, target_bin, require_bin=True)
    )
    imported = project.import_files(
        [str(path) for path in resolved],
        target_bin=bin_item,
        suppress_ui=True,
        as_numbered_stills=as_numbered_stills,
        command_name="DCC-MCP import media",
    )
    return {
        "items": [_item_data(item) for item in imported[:MAX_MEDIA_FILES]],
        "imported_count": len(imported),
        "input_bytes": total_bytes,
    }


def create_sequence(
    *, name: str, preset_path: Optional[str] = None, app_factory=Premiere
) -> dict[str, Any]:
    preset = None
    if preset_path is not None:
        preset = _allowed_path(
            preset_path,
            variable="DCC_MCP_PREMIERE_ALLOWED_PRESET_ROOTS",
            field="preset_path",
            must_exist=True,
            extensions={".sqpreset"},
        )
    created = _project(_app(app_factory)).create_sequence(
        _text(name, "name", 256),
        preset_path=str(preset) if preset is not None else None,
        command_name="DCC-MCP create sequence",
    )
    return {"sequence": _sequence_data(created), "created": True}


def _edit_project_item(
    *,
    mode: str,
    project_item: Any,
    sequence: Any = None,
    time: float = 0,
    video_track: int = 0,
    audio_track: int = 0,
    limit_shift: bool = False,
    app_factory=Premiere,
) -> dict[str, Any]:
    if not isinstance(limit_shift, bool):
        raise PremiereOperationError("limit_shift must be a boolean")
    project = _project(_app(app_factory))
    target_sequence = _sequence(project, sequence)
    item = _project_item(project, project_item)
    seconds = _number(time, "time")
    video_index = _integer(video_track, "video_track", 0, MAX_TRACKS - 1)
    audio_index = _integer(audio_track, "audio_track", 0, MAX_TRACKS - 1)
    if mode == "insert":
        result = target_sequence.insert_project_item(
            item,
            time=seconds,
            video_track=video_index,
            audio_track=audio_index,
            limit_shift=limit_shift,
            command_name="DCC-MCP insert project item",
        )
    else:
        result = target_sequence.overwrite_project_item(
            item,
            time=seconds,
            video_track=video_index,
            audio_track=audio_index,
            command_name="DCC-MCP overwrite project item",
        )
    return {
        "mode": mode,
        "sequence": _sequence_data(target_sequence),
        "project_item": _item_data(item),
        "time": seconds,
        "video_track": video_index,
        "audio_track": audio_index,
        "host_result": _json_value(result),
    }


def insert_project_item(**kwargs: Any) -> dict[str, Any]:
    return _edit_project_item(mode="insert", **kwargs)


def overwrite_project_item(**kwargs: Any) -> dict[str, Any]:
    return _edit_project_item(mode="overwrite", **kwargs)


def create_marker(
    *,
    name: str,
    start: float,
    sequence: Any = None,
    comments: Optional[str] = None,
    duration: Optional[float] = None,
    marker_type: Optional[str] = None,
    app_factory=Premiere,
) -> dict[str, Any]:
    value = _sequence(_project(_app(app_factory)), sequence)
    clean_comments = _text(comments, "comments", MAX_COMMENT) if comments is not None else None
    clean_type = _text(marker_type, "marker_type", 64) if marker_type is not None else None
    marker = value.create_marker(
        _text(name, "name", 256),
        start=_number(start, "start"),
        comments=clean_comments,
        duration=_number(duration, "duration", 0.000001) if duration is not None else None,
        marker_type=clean_type,
        command_name="DCC-MCP create marker",
    )
    return {"marker": _marker_data(marker), "created": True}


def save_project(*, app_factory=Premiere) -> dict[str, Any]:
    saved = _project(_app(app_factory)).save(command_name="DCC-MCP save project")
    path = Path(saved.path).resolve(strict=False) if saved.path else None
    evidence = _file_evidence(path) if path is not None and path.is_file() else None
    return {
        "project": _project_data(saved),
        "saved": True,
        "file_verified": evidence is not None,
        "file": evidence,
    }


def save_project_as(
    *,
    path: str,
    overwrite: bool = False,
    create_parents: bool = False,
    app_factory=Premiere,
) -> dict[str, Any]:
    target = _prepare_output(
        path,
        extensions={".prproj"},
        overwrite=overwrite,
        create_parents=create_parents,
    )
    previous = _file_state(target)
    saved = _project(_app(app_factory)).save_as(str(target), command_name="DCC-MCP save project as")
    evidence = _verified_changed_output(target, previous)
    return {"project": _project_data(saved), "saved": True, "file": evidence}


def list_encoder_presets(
    *, offset: int = 0, limit: int = 200, app_factory=Premiere
) -> dict[str, Any]:
    offset = _integer(offset, "offset", 0, 1_000_000)
    limit = _integer(limit, "limit", 1, MAX_LIST_RESULTS)
    presets = list(_app(app_factory).encoder.presets)
    page = presets[offset : offset + limit]
    return {
        "presets": [
            {
                "name": preset.name,
                "path": preset.path,
                "format": preset.format,
                "extension": preset.extension,
                "typename": preset.typename,
            }
            for preset in page
        ],
        "total": len(presets),
        "offset": offset,
        "limit": limit,
        "truncated": offset + len(page) < len(presets),
    }


def queue_sequence_export(
    *,
    output_path: str,
    preset_path: str,
    sequence: Any = None,
    overwrite: bool = False,
    create_parents: bool = False,
    start_queue_immediately: bool = True,
    app_factory=Premiere,
) -> dict[str, Any]:
    if not isinstance(start_queue_immediately, bool):
        raise PremiereOperationError("start_queue_immediately must be a boolean")
    preset = _allowed_path(
        preset_path,
        variable="DCC_MCP_PREMIERE_ALLOWED_PRESET_ROOTS",
        field="preset_path",
        must_exist=True,
        extensions={".epr"},
    )
    app = _app(app_factory)
    target_sequence = _sequence(_project(app), sequence)
    raw_extension = app.encoder.get_export_file_extension(target_sequence, str(preset))
    extension = str(raw_extension).strip().lower() if raw_extension else ""
    if extension and not extension.startswith("."):
        extension = "." + extension
    if not SAFE_EXPORT_EXTENSION.fullmatch(extension):
        raise PremiereOperationError("encoder preset did not report a safe output extension")
    target = _prepare_output(
        output_path,
        extensions={extension},
        overwrite=overwrite,
        create_parents=create_parents,
    )
    preexisting = target.is_file()
    job = target_sequence.export(
        str(target),
        preset_path=str(preset),
        export_type="QUEUE_TO_AME",
        export_full=True,
        remove_on_completion=True,
        start_queue_immediately=start_queue_immediately,
        command_name="DCC-MCP queue sequence export",
    )
    exists_after_queue = target.is_file()
    generated_during_call = exists_after_queue and not preexisting
    return {
        "job": _job_data(job),
        "queued": True,
        "output_preexisted": preexisting,
        "output_exists_after_queue": exists_after_queue,
        "output_generated_during_call": generated_during_call,
        "output": _file_evidence(target) if generated_during_call else {"path": str(target)},
    }


def export_frame(
    *,
    output_path: str,
    time: float,
    sequence: Any = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    overwrite: bool = False,
    create_parents: bool = False,
    app_factory=Premiere,
) -> dict[str, Any]:
    if (width is None) != (height is None):
        raise PremiereOperationError("width and height must be provided together")
    if width is not None:
        width = _integer(width, "width", 1, 16_384)
        height = _integer(height, "height", 1, 16_384)
        if width * height > 100_000_000:
            raise PremiereOperationError("frame dimensions exceed 100 million pixels")
    target = _prepare_output(
        output_path,
        extensions=FRAME_EXTENSIONS,
        overwrite=overwrite,
        create_parents=create_parents,
    )
    previous = _file_state(target)
    value = _sequence(_project(_app(app_factory)), sequence)
    job = value.export_frame(
        str(target),
        time=_number(time, "time"),
        width=width,
        height=height,
        command_name="DCC-MCP export frame",
    )
    evidence = _verified_changed_output(target, previous)
    return {"job": _job_data(job), "exported": True, "file": evidence}
