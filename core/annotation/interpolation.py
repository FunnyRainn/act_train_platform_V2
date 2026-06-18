from __future__ import annotations

from core import store


def interpolate_track(frame_set_id: str, track_id: str) -> dict:
    """用途：说明 标注保存、插值和预标注处理 中 `interpolate_track` 的职责和调用边界。
    入参：frame_set_id、track_id，按函数签名和调用上下文传入。
    返回：保持原函数既有返回类型和返回内容。
    副作用：可能读取或写入标注数据、轨迹数据和预标注结果。
    异常/失败语义：保持原有异常传播和失败处理语义，不新增错误处理分支。
    """

    frames = store.list_frames(frame_set_id)
    annotations = [a for a in store.list_annotations(frame_set_id) if a.get("track_id") == track_id and a.get("is_keyframe")]
    if len(annotations) < 2:
        raise ValueError("至少需要两个关键帧才能插值")

    frame_by_id = {frame["id"]: frame for frame in frames}
    frame_order = {frame["id"]: idx for idx, frame in enumerate(frames)}
    keyframes = sorted(annotations, key=lambda a: frame_order.get(a["frame_id"], 0))
    generated = 0
    # 重新插值前先清理旧的自动生成框，保留人工关键帧作为唯一事实来源。
    store.delete_track_interpolated(frame_set_id, track_id)

    for left, right in zip(keyframes, keyframes[1:]):
        left_pos = frame_order[left["frame_id"]]
        right_pos = frame_order[right["frame_id"]]
        gap = right_pos - left_pos
        if gap <= 1:
            continue
        for pos in range(left_pos + 1, right_pos):
            # 在线性插值中只补两个关键帧之间的中间帧，不覆盖左右两端关键帧。
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
