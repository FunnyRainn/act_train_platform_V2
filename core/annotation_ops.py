from __future__ import annotations

from . import store


def interpolate_track(frame_set_id: str, track_id: str) -> dict:
    frames = store.list_frames(frame_set_id)
    annotations = [a for a in store.list_annotations(frame_set_id) if a.get("track_id") == track_id and a.get("is_keyframe")]
    if len(annotations) < 2:
        raise ValueError("至少需要两个关键帧才能插值")

    frame_by_id = {frame["id"]: frame for frame in frames}
    frame_order = {frame["id"]: idx for idx, frame in enumerate(frames)}
    keyframes = sorted(annotations, key=lambda a: frame_order.get(a["frame_id"], 0))
    generated = 0
    store.delete_track_interpolated(frame_set_id, track_id)

    for left, right in zip(keyframes, keyframes[1:]):
        left_pos = frame_order[left["frame_id"]]
        right_pos = frame_order[right["frame_id"]]
        gap = right_pos - left_pos
        if gap <= 1:
            continue
        for pos in range(left_pos + 1, right_pos):
            ratio = (pos - left_pos) / gap
            frame = frames[pos]
            ann = {
                "track_id": track_id,
                "label_code": left["label_code"],
                "x": left["x"] + (right["x"] - left["x"]) * ratio,
                "y": left["y"] + (right["y"] - left["y"]) * ratio,
                "w": left["w"] + (right["w"] - left["w"]) * ratio,
                "h": left["h"] + (right["h"] - left["h"]) * ratio,
                "source": "interpolated",
                "is_keyframe": False,
                "confirmed": True,
            }
            project_id = left["project_id"]
            store.add_annotation(project_id, frame_set_id, frame["id"], ann)
            generated += 1

    return {
        "track_id": track_id,
        "generated": generated,
        "first_frame": frame_by_id[keyframes[0]["frame_id"]]["frame_index"],
        "last_frame": frame_by_id[keyframes[-1]["frame_id"]]["frame_index"],
    }
