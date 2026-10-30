"""旧矩形标注增加乐观并发控制，使用隔离SQLite与真实HTTP路由。"""
from core import db
from test_task_annotations import client  # 复用临时项目/帧集，绝不加载日常数据库。


def snapshot(client, frame="f1"):
    return client.get("/api/frame-sets/fs/annotations-snapshot", params={"frame_id": frame}).json()


def payload(revision):
    return {"project_id": "p", "frame_set_id": "fs", "frame_id": "f1", "revision": revision,
            "annotations": [{"label_code": "A1", "x": .1, "y": .2, "w": .3, "h": .4}]}


def test_browsing_is_readonly_and_stale_tab_cannot_overwrite(client):
    first = snapshot(client)
    assert first["annotations"] == [] and snapshot(client) == first
    with db.get_conn() as conn:
        assert conn.execute("SELECT count(*) FROM annotations WHERE frame_id='f1'").fetchone()[0] == 0
    saved = client.put("/api/annotations/frame", json=payload(first["revision"]))
    assert saved.status_code == 200, saved.text
    assert saved.json()["revision"] != first["revision"]
    stale = client.put("/api/annotations/frame", json={**payload(first["revision"]), "annotations": []})
    assert stale.status_code == 409
    assert snapshot(client) == saved.json()


def test_legacy_writer_invalidates_new_snapshot_and_project_mismatch_is_rejected(client):
    first = snapshot(client)
    legacy = client.post("/api/annotations/frame", json=payload(first["revision"]))
    assert legacy.status_code == 200 and isinstance(legacy.json(), list)
    assert client.put("/api/annotations/frame", json=payload(first["revision"])).status_code == 409
    current = snapshot(client)
    wrong = {**payload(current["revision"]), "project_id": "other"}
    assert client.put("/api/annotations/frame", json=wrong).status_code == 400
    assert client.post("/api/annotations/frame", json=wrong).status_code == 400
    assert snapshot(client) == current


def test_missing_revision_and_cross_frame_snapshot_are_rejected(client):
    assert client.put("/api/annotations/frame", json=payload(None)).status_code == 400
    assert client.get("/api/frame-sets/other/annotations-snapshot", params={"frame_id": "f1"}).status_code == 400
