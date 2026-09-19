"""任务明确的YOLO目录导入，先全量检查，再保存可编辑原始标注，不覆盖来源。"""
from __future__ import annotations
import json
import hashlib
import shutil
from pathlib import Path, PureWindowsPath

import cv2
import numpy as np
import yaml

from core import store
from core.db import get_conn
from core.paths import FRAMES_DIR
from core.task_annotations import MAX_PIXELS, get_set, normalize_objects
from core.task_contract import task_type
from core.utils import IMAGE_SUFFIXES, new_id


def local_child(root: Path, value: str) -> Path:
    """所有数据文件限制在用户选定目录，拒绝绝对路径/符号链接逃逸。"""
    part=Path(value)
    if part.is_absolute() or PureWindowsPath(value).drive or ".." in part.parts or ".." in PureWindowsPath(value).parts:
        raise ValueError(f"数据集内部路径必须是安全相对路径: {value}")
    target=(root/part).resolve()
    if not target.is_relative_to(root): raise ValueError("数据文件通过符号链接越出选定目录")
    return target


def parse_objects(path: Path, spec: dict) -> list[dict]:
    """检测只能5列，实例只能多边形；缺标签不是已确认负样本，明确拒绝。"""
    if not path.is_file(): raise ValueError(f"缺少标签文件，不能自动当负样本: {path.name}")
    objects=[]
    for number,line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(),1):
        if not line.strip(): continue
        values=line.split()
        try:
            cls=int(values[0]); coords=[float(value) for value in values[1:]]
        except ValueError as exc: raise ValueError(f"{path.name}:{number}包含非法数值") from exc
        if not 0<=cls<len(spec["label_codes"]): raise ValueError(f"{path.name}:{number}类别越界")
        item={"instance_id":f"import-{number}","label_code":spec["label_codes"][cls]}
        if spec["task_type"]=="detect":
            if len(coords)!=4: raise ValueError(f"{path.name}:{number}检测标签应为5列，不可混入多边形")
            x,y,w,h=coords
            if w<=0 or h<=0: raise ValueError("检测框宽高必须为正")
            item["bbox"]=[x-w/2,y-h/2,x+w/2,y+h/2]
        else:
            if len(coords)<6 or len(coords)%2: raise ValueError(f"{path.name}:{number}实例标签需要至少3个二维顶点")
            item["polygons"]=[list(map(list,zip(coords[::2],coords[1::2])))]
        objects.append(item)
    return normalize_objects(spec,objects)


def inspect_source(project_id: str, task: str, source_dir: str) -> tuple[dict,list]:
    """扫描不生成任何副本，记录路径而非累积解码像素；只支持目录型拆分。"""
    task_type(task)
    root=Path(source_dir).expanduser().resolve()
    if not Path(source_dir).is_absolute() or not root.is_dir(): raise ValueError("请选择服务器本机已有数据集绝对目录")
    yaml_file=next((root/name for name in ("dataset.generated.yaml","data.yaml","dataset.yaml") if (root/name).is_file()),None)
    if yaml_file is None: raise ValueError("未找到data.yaml或dataset.generated.yaml")
    local_child(root,yaml_file.name)
    config=yaml.safe_load(yaml_file.read_text(encoding="utf-8-sig"))
    if not isinstance(config,dict): raise ValueError("数据集YAML必须为映射")
    if config.get("task_type",task)!=task: raise ValueError("所选任务与数据集任务声明不一致")
    names=config.get("names")
    if isinstance(names,dict):
        names={int(k):v for k,v in names.items()}
        if sorted(names)!=list(range(len(names))): raise ValueError("类别索引必须从0连续")
        names=[names[k] for k in range(len(names))]
    if not isinstance(names,list) or not names or any(not isinstance(n,str) or not n.strip() for n in names) or len(set(names))!=len(names): raise ValueError("类别names缺失或重复")
    labels=names
    if task=="semantic_segment":
        if names[0]!="__background__" or len(names)>255: raise ValueError("语义导入要求类别0为__background__，忽略255，最多254前景类")
        labels=names[1:]
    project=store.get_project(project_id)
    if not labels or any(code not in project["label_codes"] for code in labels): raise ValueError("names必须对应当前项目标签编码；请先在项目配置这些编码")
    spec={"project_id":project_id,"task_type":task,"label_codes":labels}
    prepared=[]; seen=set()
    for split in ("train","val","test"):
        value=config.get(split)
        if not value: continue
        if not isinstance(value,str): raise ValueError("当前导入仅支持train/val/test目录路径，不支持列表或TXT清单")
        image_dir=local_child(root,value)
        if not image_dir.is_dir(): raise ValueError(f"拆分目录不存在: {split}")
        relative=image_dir.relative_to(root)
        if not relative.parts or relative.parts[0]!="images": raise ValueError("图片目录需采用images/train、images/val等YOLO标准结构")
        label_dir=local_child(root,str(Path("labels",*relative.parts[1:])))
        mask_dir=local_child(root,str(Path(str(config.get("masks_dir") or "masks"),*relative.parts[1:])))
        for image_path in sorted(image_dir.rglob("*")):
            if image_path.suffix.lower() not in IMAGE_SUFFIXES or not image_path.is_file(): continue
            source=local_child(root,str(image_path.relative_to(root)))
            if source in seen: raise ValueError("同一图片被多个拆分重复引用")
            seen.add(source)
            if len(seen)>10000: raise ValueError("单次导入最多10000张图片，请分成明确批次")
            image=cv2.imread(str(source))
            if image is None or image.shape[0]*image.shape[1]>MAX_PIXELS: raise ValueError(f"图片无法读取或超过像素上限: {image_path.name}")
            sub=image_path.relative_to(image_dir)
            annotation_path=(mask_dir/sub.with_suffix(".png")) if task=="semantic_segment" else (label_dir/sub.with_suffix(".txt"))
            annotation_path=local_child(root,str(annotation_path.relative_to(root)))
            if task=="semantic_segment":
                mask=cv2.imread(str(annotation_path),cv2.IMREAD_UNCHANGED)
                if mask is None or mask.ndim!=2 or mask.dtype!=np.uint8 or mask.shape!=image.shape[:2]: raise ValueError(f"语义mask必须是同尺寸单通道uint8类别图: {sub}")
                if not set(np.unique(mask).tolist()) <= set(range(len(names)))|{255}: raise ValueError(f"语义mask含未定义类别: {sub}")
            else: parse_objects(annotation_path,spec)
            # 预检记录内容指纹，复制提交前再次核验，避免长导入期间来源被替换。
            prepared.append((source,annotation_path,image.shape[1],image.shape[0],split,hashlib.sha256(source.read_bytes()).hexdigest(),hashlib.sha256(annotation_path.read_bytes()).hexdigest()))
    if not prepared: raise ValueError("数据集中没有可导入图片")
    return spec,prepared


def import_set(project_id: str, name: str, task: str, source_dir: str) -> dict:
    """校验后复制选中素材一次；事务提交原始标注，后续训练仍需显式导出版本。"""
    if not name.strip(): raise ValueError("标注集名称不能为空")
    spec,prepared=inspect_source(project_id,task,source_dir)
    set_id,frame_set_id,video_id=new_id("annotation_set"),new_id("frameset"),new_id("images")
    destination=FRAMES_DIR/project_id/frame_set_id
    destination.mkdir(parents=True,exist_ok=False)
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT INTO task_annotation_sets(id,project_id,name,task_type,labels_json,revision) VALUES(?,?,?,?,?,?)",(set_id,project_id,name.strip(),task,json.dumps(spec["label_codes"]),len(prepared)))
        conn.execute("INSERT INTO videos(id,project_id,name,source_type,path,frame_count) VALUES(?,?,?,?,?,?)",(video_id,project_id,name,"image_dataset",str(destination),len(prepared)))
        conn.execute("INSERT INTO frame_sets(id,project_id,video_id,name,output_dir,sample_every_n_frames,frame_count,status,config_json) VALUES(?,?,?,?,?,1,?,'finished',?)",(frame_set_id,project_id,video_id,name,str(destination),len(prepared),json.dumps({"source_type":"yolo_import","task_type":task})))
        source_splits={}
        for index,(source,annotation_path,width,height,split,image_hash,label_hash) in enumerate(prepared):
            frame_id=new_id("frame"); target=destination/(frame_id+source.suffix.lower())
            shutil.copy2(source,target)
            label_bytes=annotation_path.read_bytes()
            if hashlib.sha256(target.read_bytes()).hexdigest()!=image_hash or hashlib.sha256(label_bytes).hexdigest()!=label_hash:
                raise ValueError("导入期间来源内容变化，已回滚数据库；请保持数据集不变后重试")
            source_splits[frame_id]=split
            conn.execute("INSERT INTO frames(id,frame_set_id,video_id,frame_index,path,width,height) VALUES(?,?,?,?,?,?,?)",(frame_id,frame_set_id,video_id,index,str(target),width,height))
            objects=parse_objects(annotation_path,spec) if task!="semantic_segment" else []
            png=label_bytes if task=="semantic_segment" else None
            conn.execute("INSERT INTO task_frame_annotations(set_id,frame_id,payload_json,mask_png,revision) VALUES(?,?,?,?,1)",(set_id,frame_id,json.dumps({"objects":objects},ensure_ascii=False),png))
        # 拆分是数据来源的一部分；后续导出优先保留，不能自动把测试图放进训练集。
        conn.execute("UPDATE frame_sets SET config_json=? WHERE id=?",(json.dumps({"source_type":"yolo_import","task_type":task,"source_splits":source_splits}),frame_set_id))
    return {"annotation_set":get_set(set_id),"frame_set_id":frame_set_id,"frame_count":len(prepared),"source_preserved":True}
