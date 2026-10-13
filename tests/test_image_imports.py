"""真实API/SQLite检验原图任务；测试路径不接触用户素材或日常数据库。"""
import io
import sqlite3
from PIL import Image
import pytest
from fastapi.testclient import TestClient
from core import db, image_imports as service
from web.routes import image_imports as routes
from web.app_factory import create_app


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(db, "ensure_runtime_dirs", lambda:None)
    monkeypatch.setattr(service, "ASSETS_DIR", tmp_path / "assets")
    monkeypatch.setattr(service, "FRAMES_DIR", tmp_path / "frames")
    monkeypatch.setattr(routes, "UPLOADS_DIR", tmp_path / "uploads")
    with TestClient(create_app()) as client:
        with db.get_conn() as conn:
            conn.execute("INSERT INTO projects(id,name) VALUES('p','原图测试')")
        yield client


def png(number=1):
    output=io.BytesIO(); Image.new('RGB',(20,12),(number,20,30)).save(output,format='PNG')
    return output.getvalue()


def descriptor(data, name='中文/图片.png', group='拍摄片段A', split=''):
    return dict(relative_path=name, size=len(data), last_modified=123, source_group=group, split=split)


def job(api, rows, **kw):
    response=api.post('/api/image-imports',json=dict(project_id='p',name='原图素材集',client_key=kw.pop('client_key','key'),files=rows,**kw))
    assert response.status_code==200,response.text
    return response.json()


def put(api, task, index, data):
    return api.put(f'/api/image-imports/{task["id"]}/files/{index}',content=data)


def test_idempotency_dedupe_append_and_no_annotations(api):
    data=png(); rows=[descriptor(data),descriptor(data,'另一个目录/同名.png')]
    task=job(api,rows); assert job(api,rows)['id']==task['id']
    a=put(api,task,0,data); b=put(api,task,1,data)
    assert a.status_code==b.status_code==200
    assert b.json()['state']=='duplicate'
    assert a.json()['frame_id']==b.json()['frame_id']
    assert put(api,task,0,data).json()['reused']
    append=job(api,[descriptor(png(2),'新增.png')],client_key='append',frame_set_id=task['frame_set_id'])
    assert put(api,append,0,png(2)).status_code==200
    with db.get_conn() as conn:
        assert conn.execute('SELECT count(*) FROM frames').fetchone()[0]==2
        assert conn.execute('SELECT count(*) FROM image_assets').fetchone()[0]==2
        assert conn.execute('SELECT count(*) FROM task_frame_annotations').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM annotations').fetchone()[0]==0


def test_cancellation_bad_images_retry_and_completed_identity(api):
    data=png(); task=job(api,[descriptor(data)])
    assert api.post(f'/api/image-imports/{task["id"]}/cancel').status_code==200
    assert put(api,task,0,data).status_code==400
    assert api.post(f'/api/image-imports/{task["id"]}/resume').status_code==200
    assert put(api,task,0,b'X'*len(data)).status_code==400
    assert api.get(f'/api/image-imports/{task["id"]}').json()['counts']['failed']==1
    assert put(api,task,0,data).status_code==200
    assert put(api,task,0,png(2)).status_code==400
    assert not list((routes.UPLOADS_DIR/'image_imports').glob('*.part'))


@pytest.mark.parametrize('name',['../a.png','C:\\a.png','/root/a.png','a/../../a.png','bad.exe'])
def test_unsafe_path_rejected(api,name):
    response=api.post('/api/image-imports',json=dict(project_id='p',name='n',client_key='bad',files=[descriptor(png(),name)]))
    assert response.status_code==400


def test_3000_metadata_pagination_and_stable_id(api):
    # 确定性仓储测试不是浏览器3000张验收；完整浏览器上传另有证据。
    rows=[descriptor(png(),f'素材/{i:04}.png') for i in range(3000)]
    task=job(api,rows)
    assert task['total']==3000 and len(task['items'])==100
    assert api.get(f'/api/image-imports/{task["id"]}?offset=2900').json()['items'][-1]['ordinal']==2999
    for n in [0,1499,2999]: assert put(api,task,n,png()).status_code==200
    # 相同内容只产生一个frame；同时验证浏览不写空标注。
    page=api.get(f'/api/frame-sets/{task["frame_set_id"]}/frames-page').json()
    assert page['total']==1
    located=api.get(f'/api/frame-sets/{task["frame_set_id"]}/frames-page?frame_id={page["items"][0]["id"]}').json()
    assert located['position']==0
    assert api.get(f'/api/frame-sets/{task["frame_set_id"]}/frames-page?limit=101').status_code==400


def test_additive_migration_and_restore(api,tmp_path):
    task=job(api,[descriptor(png())]); put(api,task,0,png())
    # 一次一致性恢复点，随后重复迁移不影响素材引用和任务状态。
    restored=tmp_path/'restored.sqlite3'
    with db.connect() as src, sqlite3.connect(restored) as dst: src.backup(dst)
    db.init_db(); db.init_db()
    with sqlite3.connect(restored) as conn:
        assert conn.execute('SELECT count(*) FROM frames').fetchone()[0]==1
        assert conn.execute('SELECT state FROM image_import_jobs').fetchone()[0]=='finished'
