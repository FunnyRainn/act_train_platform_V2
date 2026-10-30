"""导出前显式预览来源划分；不足两个来源时不悄悄随机拆近重复帧。"""
import hashlib
import json
from collections import Counter
from pathlib import Path

from core.db import get_conn
from core.task_annotations import get_set


def preview(set_id: str, *, allow_frame_split: bool = False, split_by_video: dict | None = None) -> dict:
    """从同一读快照构造分配和摘要，不解码图片、不创建导出目录。

    既有来源拆分优先；原图按真实拍摄组，视频按原资产身份，不按别名帧集。
    allow_frame_split 是用户明确认可非精度验收用途，不能由后端自行置真。
    """
    get_set(set_id)
    if type(allow_frame_split) is not bool: raise ValueError("风险确认必须为布尔值")
    with get_conn() as conn:
        conn.execute("BEGIN")
        revision = conn.execute("SELECT revision FROM task_annotation_sets WHERE id=?", (set_id,)).fetchone()[0]
        rows = [dict(row) for row in conn.execute("""
            SELECT a.frame_id,a.revision,f.video_id,fs.config_json,v.asset_id,v.path,
                   s.source_group,s.split,ia.sha256
            FROM task_frame_annotations a JOIN frames f ON f.id=a.frame_id
            JOIN frame_sets fs ON fs.id=f.frame_set_id JOIN videos v ON v.id=f.video_id
            LEFT JOIN frame_image_sources s ON s.frame_id=f.id
            LEFT JOIN image_assets ia ON ia.id=s.asset_id
            WHERE a.set_id=? ORDER BY a.frame_id
        """, (set_id,))]
    if len(rows)<2: raise ValueError("至少保存两张标注图片，分别用于训练和验证")
    if split_by_video is not None and (not isinstance(split_by_video, dict) or set(split_by_video)!= {row['video_id'] for row in rows}
            or not set(split_by_video.values()) <= {'train','val','test'}):
        raise ValueError("视频分组划分必须完整覆盖当前视频且取值为train/val/test")
    groups, declared, assignments, identity_splits = {}, {}, {}, {}
    for row in rows:
        cfg=json.loads(row['config_json'])
        split=row['split'] or cfg.get('source_splits',{}).get(row['frame_id'],'')
        source=row['source_group'] or cfg.get('source_groups',{}).get(row['frame_id'])
        video_identity=str(row['asset_id'] or Path(row['path']).resolve())
        # 外部YOLO拆分已被显式声明而缺拍摄组时，保留声明，不反向臆测相同视频来源。
        group=f"capture:{source}" if source else f"declared:{video_identity}:{split}" if split else f"video:{video_identity}"
        if split_by_video is not None:
            requested=split_by_video[row['video_id']]
            if split and split!=requested: raise ValueError("视频分组与已声明拆分冲突，不自动移动样本")
            split=requested
        groups.setdefault(group,[]).append(row['frame_id'])
        if split:
            if group in declared and declared[group]!=split: raise ValueError("同一来源跨拆分，请检查拍摄来源声明")
            if row['sha256'] and row['sha256'] in identity_splits and identity_splits[row['sha256']]!=split:
                raise ValueError("相同原图不能跨训练、验证和测试")
            declared[group]=split
            if row['sha256']: identity_splits[row['sha256']]=split
        row.update(group=group,declared_split=split)
    unknown=sorted((group for group in groups if group not in declared),key=lambda group:(-len(groups[group]),group))
    # 保留旧视频分组导出的元数据名称，避免旧训练记录/外部读取方被重新解释。
    policy='video_source_groups' if split_by_video is not None else 'preserved_import_source' if not unknown else 'source_groups'
    requires_choice=len(groups)<2 and bool(unknown)
    warnings=[]
    if requires_choice and allow_frame_split:
        # 明确确认后仍使用确定性顺序，保留已声明拆分，不将测试集拿去训练。
        policy='acknowledged_frame_hash_not_accuracy_benchmark'
        warnings.append('同来源帧可能近重复；本划分仅支持内部功能验证，不能当作独立准确率评估。')
        ordered=sorted(rows,key=lambda row:hashlib.sha256(row['frame_id'].encode()).hexdigest())
        val_count=max(1,round(len(ordered)*.2))
        assignments={row['frame_id']:('val' if index<val_count else 'train') for index,row in enumerate(ordered)}
        requires_choice=False
    elif not requires_choice:
        # 未声明的来源先保留为整组；优先补齐train/val，有三个来源时再留测试组。
        values=set(declared.values())
        for required in ('train','val'):
            if required not in values and unknown:
                group=unknown.pop(0 if required=='train' else -1);declared[group]=required;values.add(required)
        if 'test' not in values and len(groups)>=3 and unknown: declared[unknown.pop()]='test'
        declared.update({group:'train' for group in unknown})
        assignments={row['frame_id']:declared[row['group']] for row in rows}
    if requires_choice:
        warnings.append('只有一个拍摄来源；请补充独立来源，或明确确认按帧划分的泄漏风险后继续。')
    elif not {'train','val'} <= set(assignments.values()):
        raise ValueError("当前已声明拆分未同时包含训练和验证，不能自动移动样本")
    # 内容相同的图即使位于不同帧集，也不能因两次导入落入不同拆分。
    assigned_hashes={}
    for row in rows:
        if assignments and row['sha256']:
            split=assignments[row['frame_id']]
            if row['sha256'] in assigned_hashes and assigned_hashes[row['sha256']]!=split:
                raise ValueError('划分包含跨集合重复原图，请去除重复标注引用或按来源分组')
            assigned_hashes[row['sha256']]=split
    fingerprint={'set_revision':revision,'rows':[(r['frame_id'],r['revision'],r['group'],r['declared_split'],r['sha256']) for r in rows],
                 'assignments':assignments,'policy':policy}
    digest=hashlib.sha256(json.dumps(fingerprint,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return {'preview_hash':digest,'annotation_revision':revision,'annotation_revisions':{r['frame_id']:r['revision'] for r in rows},
            'assignments':assignments,'policy':policy,'requires_choice':requires_choice,'warnings':warnings,
            'frame_count':len(rows),'counts':dict(Counter(assignments.values())),
            'groups':[{'source':group,'count':len(ids),'split':declared.get(group,
                       '按帧拆分（已确认风险）' if policy=='acknowledged_frame_hash_not_accuracy_benchmark' else '需确认')}
                      for group,ids in groups.items()]}
