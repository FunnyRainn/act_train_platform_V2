"""真实SQLite/API验证三任务原始标注、导出和增量迁移，所有写入仅在测试目录。"""
import json
import sqlite3
from pathlib import Path

import cv2
import numpy as np
import pytest
import yaml
from fastapi.testclient import TestClient

from core import db, task_annotations as annotations, task_dataset, task_importer
from web.app_factory import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """从旧schema建立数据库，再运行新schema，验证旧矩形数据不被覆盖。"""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(db, "ensure_runtime_dirs", lambda: None)
    monkeypatch.setattr(task_dataset, "DATASETS_DIR", tmp_path / "datasets")
    monkeypatch.setattr(task_importer, "FRAMES_DIR", tmp_path / "imported_frames")
    schema = Path(db.__file__).with_name("schema.sql").read_text(encoding="utf-8")
    old_schema = schema[schema.index("CREATE TABLE IF NOT EXISTS labels"):]
    with db.get_conn() as conn:
        conn.executescript(old_schema)
        conn.execute("INSERT INTO labels(code,group_code,name) VALUES('A1','A','细长对象')")
        conn.execute("INSERT INTO projects(id,name,label_codes_json) VALUES('p','合成测试','[\"A1\"]')")
        conn.execute("INSERT INTO videos(id,project_id,name,source_type,path) VALUES('v','p','合成','synthetic','test')")
        conn.execute("INSERT INTO frame_sets(id,project_id,video_id,name,output_dir,sample_every_n_frames) VALUES('fs','p','v','合成帧集',?,1)", (str(tmp_path),))
        for i in range(3):
            image = np.full((32, 48, 3), 40, np.uint8)
            cv2.rectangle(image, (8+i,4), (12+i,28), (240,240,240), -1)
            path = tmp_path / f"{i}.png"
            assert cv2.imwrite(str(path), image)
            conn.execute("INSERT INTO frames(id,frame_set_id,video_id,frame_index,path,width,height) VALUES(?,'fs','v',?,?,48,32)", (f"f{i}",i,str(path)))
        conn.execute("INSERT INTO annotations(id,project_id,frame_set_id,frame_id,label_code,x,y,w,h) VALUES('legacy','p','fs','f0','A1',.1,.1,.2,.2)")
    with TestClient(create_app()) as api:
        yield api
    with db.get_conn() as conn:
        assert conn.execute("SELECT w FROM annotations WHERE id='legacy'").fetchone()[0] == .2


def make_set(client, task):
    response = client.post("/api/annotation-sets", json={"project_id":"p","name":task,"task_type":task})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def object_payload(task, fragments=1):
    item = {"instance_id":"one","label_code":"A1"}
    if task == "detect":
        item["bbox"] = [.2,.1,.3,.9]
    else:
        item["polygons"] = [[[.2,.1],[.3,.1],[.3,.9],[.2,.9]]] * fragments
    return {"revision":0,"objects":[item]}


@pytest.mark.parametrize("task", ["detect","instance_segment","semantic_segment"])
def test_save_reload_export_and_restore(client, task, tmp_path):
    set_id = make_set(client, task)
    for i in range(3):
        url = f"/api/annotation-sets/{set_id}/frames/f{i}"
        empty = client.get(url).json()
        assert empty["revision"] == 0
        if task == "semantic_segment":
            assert empty["mask_rle"] == [255,1536]
            mask = np.zeros((32,48),np.uint8); mask[4:28,8:12] = 1; mask[:2] = 255
            payload = {"revision":0,"mask_rle":annotations.encode_rle(mask)}
        else:
            payload = object_payload(task)
        saved = client.put(url,json=payload)
        assert saved.status_code == 200, saved.text
        assert client.get(url).json() == saved.json()
        assert client.put(url,json=payload).status_code == 400
    exported = client.post(f"/api/annotation-sets/{set_id}/export",json={"name":"版本1"})
    assert exported.status_code == 200, exported.text
    result = exported.json(); output = Path(result["output_dir"])
    assert result["metadata"]["task_type"] == task
    config = yaml.safe_load((output/"dataset.generated.yaml").read_text())
    assert config["task_type"] == task
    assert len(list((output/"images/train").glob("*.png"))) == 2
    assert len(list((output/"images/val").glob("*.png"))) == 1
    if task == "semantic_segment":
        for path in (output/"masks").rglob("*.png"):
            assert np.array_equal(cv2.imread(str(path),cv2.IMREAD_UNCHANGED), mask)
        assert config["names"] == {0:"__background__",1:"A1"}
    else:
        assert all(len(p.read_text().split()) == (5 if task=="detect" else 9) for p in (output/"labels").rglob("*.txt"))
    # 测试库一次SQLite在线备份并恢复，不复制用户业务数据库。
    with db.connect() as source, sqlite3.connect(tmp_path/"restore.sqlite3") as restored:
        source.backup(restored)
        assert restored.execute("SELECT count(*) FROM task_frame_annotations").fetchone()[0] == 3
        assert restored.execute("SELECT count(*) FROM annotations").fetchone()[0] == 1


def test_multifragment_preserved_and_export_refused(client):
    set_id = make_set(client,"instance_segment")
    for i in range(2):
        result = client.put(f"/api/annotation-sets/{set_id}/frames/f{i}",json=object_payload("instance_segment",2))
        assert result.status_code == 200
        assert len(result.json()["objects"][0]["polygons"]) == 2
    response = client.post(f"/api/annotation-sets/{set_id}/export",json={})
    assert response.status_code == 400 and "one" in response.text


def test_video_groups_preserve_test_split(client):
    """三个真实来源分组不得按相邻帧随机拆分，显式覆盖必须完整且不冲突。"""
    with db.get_conn() as conn:
        for index in (1, 2):
            conn.execute("INSERT INTO videos(id,project_id,name,source_type,path) VALUES(?,'p',?,'video',?)", (f"v{index}", f"clip{index}", f"clip{index}.mp4"))
            conn.execute("UPDATE frames SET video_id=? WHERE id=?", (f"v{index}", f"f{index}"))
    set_id = make_set(client, "detect")
    for index in range(3):
        assert client.put(f"/api/annotation-sets/{set_id}/frames/f{index}", json=object_payload("detect")).status_code == 200
    splits = {"v": "train", "v1": "val", "v2": "test"}
    response = client.post(f"/api/annotation-sets/{set_id}/export", json={"split_by_video": splits})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["metadata"]["split_policy"] == "video_source_groups"
    index = json.loads((Path(result["output_dir"]) / "annotation_index.json").read_text())
    assert {row["video_id"]: row["split"] for row in index} == splits
    assert result["summary"]["test_count"] == 1
    assert client.post(f"/api/annotation-sets/{set_id}/export", json={"split_by_video": {"v": "train"}}).status_code == 400
    with db.get_conn() as conn:
        conn.execute("UPDATE videos SET path='test' WHERE id='v1'")
    conflict = client.post(f"/api/annotation-sets/{set_id}/export", json={"split_by_video": splits})
    assert conflict.status_code == 400 and "同一来源" in conflict.text


@pytest.mark.parametrize("runs", [[256,1536],[1,1535],[1,1537],[1,-1],[1,True],[1,1.5],[1,1536,0]])
def test_invalid_semantic_rle_rejected(runs):
    with pytest.raises(ValueError):
        annotations.decode_rle(runs,48,32,1)


def test_crop_boundary_and_mismatch(client):
    bounds = task_dataset.crop_bounds(100,100,[.2,.2,.5,.5])
    line = task_dataset.object_labels({"task_type":"detect","label_codes":["A1"]},[{"bbox":[0,0,.5,.5],"label_code":"A1"}],100,100,bounds)[0]
    assert line == "0 0.30000000 0.30000000 0.60000000 0.60000000"
    with pytest.raises(ValueError): task_dataset.crop_bounds(10,10,[.9,0,.2,.5])
    set_id = make_set(client,"detect")
    response = client.put(f"/api/annotation-sets/{set_id}/frames/f0",json={"revision":0,"mask_rle":[0,1536]})
    assert response.status_code == 400
    with db.get_conn() as conn:
        conn.execute("INSERT INTO projects(id,name,label_codes_json) VALUES('other','其他项目','[\"A1\"]')")
    other = annotations.create_set("other","独立","detect")
    assert client.get(f"/api/annotation-sets/{other['id']}/frames/f0").status_code == 400


def test_editor_page_is_real_route(client):
    response = client.get("/task-annotate")
    assert response.status_code == 200 and "ta-canvas" in response.text


@pytest.mark.parametrize("task", ["detect","instance_segment","semantic_segment"])
def test_yolo_import_export_roundtrip(client,task):
    set_id=make_set(client,task)
    for i in range(2):
        payload={"revision":0,"mask_rle":[255,96,0,900,1,540]} if task=="semantic_segment" else object_payload(task)
        assert client.put(f"/api/annotation-sets/{set_id}/frames/f{i}",json=payload).status_code==200
    exported=client.post(f"/api/annotation-sets/{set_id}/export",json={}).json()
    source=Path(exported["output_dir"])
    # 记录全部源文件内容哈希，导入不得覆盖、转换或重写来源。
    import hashlib
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob("*") if p.is_file()}
    request={"project_id":"p","name":"导入","task_type":task,"source_dir":str(source)}
    preview=client.post("/api/task-datasets/inspect",json=request)
    assert preview.status_code==200 and preview.json()["frame_count"]==2
    imported=client.post("/api/task-datasets/import",json=request)
    assert imported.status_code==200,imported.text
    result=imported.json(); imported_id=result["annotation_set"]["id"]
    frames=client.get(f"/api/frame-sets/{result['frame_set_id']}/frames").json()
    assert len(frames)==2
    for frame in frames:
        raw=client.get(f"/api/annotation-sets/{imported_id}/frames/{frame['id']}").json()
        if task=="semantic_segment": assert raw["mask_rle"]==payload["mask_rle"]
        else:
            saved=raw["objects"][0]
            expected=payload["objects"][0]
            assert saved["label_code"]==expected["label_code"]
            assert np.allclose(saved.get("bbox",saved.get("polygons")),expected.get("bbox",expected.get("polygons")))
    reexport=client.post(f"/api/annotation-sets/{imported_id}/export",json={})
    assert reexport.status_code==200
    assert reexport.json()["metadata"]["split_policy"]=="preserved_import_source"
    assert reexport.json()["summary"]["train_count"]==1
    assert reexport.json()["summary"]["val_count"]==1
    after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob("*") if p.is_file()}
    assert before==after


def test_import_traversal_and_task_mismatch(client,tmp_path):
    set_id=make_set(client,"instance_segment")
    for i in range(2): client.put(f"/api/annotation-sets/{set_id}/frames/f{i}",json=object_payload("instance_segment"))
    exported=client.post(f"/api/annotation-sets/{set_id}/export",json={}).json()
    request={"project_id":"p","name":"禁止混用","task_type":"detect","source_dir":exported["output_dir"]}
    assert client.post("/api/task-datasets/inspect",json=request).status_code==400
    with pytest.raises(ValueError): task_importer.local_child(tmp_path.resolve(),"../escape")
    with pytest.raises(ValueError): task_importer.local_child(tmp_path.resolve(),"C:\\private\\mask.png")
