/* 原图只由 File 对象流式发送；不预览/解码整批图片，任务状态以服务端为准。 */
(() => {
  'use strict';
  const el = id => document.getElementById(`images-${id}`);
  let limits, files = [], selected = null, running = false, controllers = new Set(), generation = 0;
  const project = () => document.getElementById('active-project').value;
  const identity = item => JSON.stringify([item.relative_path, item.size ?? item.byte_size, item.last_modified]);
  const fileInfo = file => ({relative_path:file.webkitRelativePath || file.name, size:file.size, last_modified:file.lastModified});
  const safe = fn => async event => {try {await fn(event);} catch(error) {el('status').textContent=error.message; showToast(error.message,'error');}};
  function locked(value, {allowCancel=true}={}) {
    running=value;
    for (const id of ['start','resume','jobs','files','folder','name','group','split','target']) el(id).disabled=value;
    document.getElementById('active-project').disabled=value;
    el('cancel').disabled=!value || !allowCancel;
  }
  function draw(task) {
    const c=task.counts || {}, done=(c.completed||0)+(c.duplicate||0), failed=c.failed||0;
    el('progress').max=task.total || 1; el('progress').value=done+failed;
    el('status').textContent=`任务${task.state==='cancelled'?'已取消':task.state==='finished'?'已完成':running?'上传中':'可继续'}：完成 ${c.completed||0}，重复复用 ${c.duplicate||0}，失败 ${failed}，剩余 ${task.total-done-failed} / ${task.total}。`;
    el('open').hidden=!done; el('open').href=`/task-annotate?project_id=${encodeURIComponent(task.project_id)}&frame_set_id=${encodeURIComponent(task.frame_set_id)}`;
  }
  function rememberTask(task) {
    try {localStorage.setItem(`image-import:${task.project_id}`,task.id);} catch (_) { /* 状态仍可从任务列表恢复 */ }
  }
  async function refresh({preserve=false}={}) {
    if(running) return;
    const token=++generation, id=project(), previousTarget=el('target').value,
      retained=preserve && selected?.project_id===id ? selected : null; selected=retained;
    const [jobs,sets]=id?await Promise.all([apiGet(`/api/image-imports?project_id=${encodeURIComponent(id)}`),apiGet(`/api/frame-sets?project_id=${encodeURIComponent(id)}`)]):[[],[]];
    if(token!==generation) return;
    fillSelect(el('jobs'),jobs,row=>row.id,row=>`${row.created_at} · ${row.done}/${row.total} · ${row.state}`,'选择最近导入任务');
    fillSelect(el('target'),sets.filter(row=>row.config?.source_type==='browser_images'),row=>row.id,row=>`${row.name}（${row.frame_count}张）`,'新建素材集');
    if(sets.some(row=>row.id===previousTarget)) el('target').value=previousTarget;
    let last=retained?.id;
    if(!last) try {last=localStorage.getItem(`image-import:${id}`);} catch (_) { /* 本地存储不可用时手选任务 */ }
    if(last && jobs.some(row=>row.id===last)) {
      const task=retained || await apiGet(`/api/image-imports/${encodeURIComponent(last)}`);
      if(token!==generation) return;
      selected=task;el('jobs').value=last;draw(task);
    }
  }
  for(const id of ['files','folder']) el(id).onchange=safe(async()=>{
    if(!limits) throw Error('导入限制尚未加载，请稍后重试');
    const chosen=Array.from(el(id).files || []);
    files=chosen.filter(file=>limits.extensions.some(ext=>file.name.toLowerCase().endsWith(ext)));
    // 文件选择器枚举顺序不稳定；仅为新任务排序，既有任务仍按持久ordinal恢复。
    const collator=new Intl.Collator('zh-CN',{numeric:true,sensitivity:'variant'});
    files.sort((left,right)=>collator.compare(fileInfo(left).relative_path,fileInfo(right).relative_path));
    if(files.length>limits.files) {files=[]; throw Error(`一次最多 ${limits.files} 张`);}
    if(files.some(file=>!file.size || file.size>limits.file_bytes)) {files=[]; throw Error('含空文件或超过32MiB的文件，请重新选择');}
    el(id==='files'?'folder':'files').value='';
    el('selected').textContent=`已选择 ${files.length} 张原图；忽略 ${chosen.length-files.length} 个非图片文件。来源组需要与真实拍摄片段一致。`;
  });
  el('jobs').onchange=safe(async()=>{
    const id=el('jobs').value, token=++generation;
    const task=id?await apiGet(`/api/image-imports/${encodeURIComponent(id)}`):null;
    if(token!==generation) return; selected=task; if(task) {rememberTask(task);draw(task);}
  });
  async function uploadTask(task) {
    locked(true); selected=task; rememberTask(task); el('errors').textContent=''; draw(task);
    const available=new Map(files.map(file=>[identity(fileInfo(file)),file]));
    let pending=[], messages=[], stopped=false;
    try {
      // 只读取有界分页的元数据；不读取所有图片像素，也不要求重新选择已成功文件。
      for(let offset=0;offset<task.total;offset+=limits.page_size) {
        const page=offset===0?task:await apiGet(`/api/image-imports/${task.id}?offset=${offset}`);
        for(const item of page.items) if(!['completed','duplicate'].includes(item.state)) {
          const file=available.get(identity(item));
          if(file) pending.push({item,file}); else messages.push(`${item.relative_path}：请重新选择原文件（大小/修改时间须匹配）`);
        }
      }
      if(task.state==='cancelled') task=await apiPost(`/api/image-imports/${task.id}/resume`,{});
      let cursor=0;
      async function worker() {
        while(!stopped && running && cursor<pending.length) {
          const {item,file}=pending[cursor++], controller=new AbortController(); controllers.add(controller);
          try {
            const response=await fetch(`/api/image-imports/${task.id}/files/${item.ordinal}`,{method:'PUT',body:file,signal:controller.signal,headers:{'Content-Type':'application/octet-stream'}});
            const result=await parseApiResponse(response);
            task.counts[item.state]=Math.max(0,(task.counts[item.state]||0)-1);
            task.counts[result.state]=(task.counts[result.state]||0)+1;
          } catch(error) {
            if(error.name==='AbortError') {stopped=true; break;}
            messages.push(`${item.relative_path}：${error.message}`);
            if(item.state!=='failed') {task.counts[item.state]=Math.max(0,(task.counts[item.state]||0)-1);task.counts.failed=(task.counts.failed||0)+1;}
          } finally {controllers.delete(controller); draw(task);}
        }
      }
      await Promise.all(Array.from({length:limits.parallel_uploads},worker));
      selected=await apiGet(`/api/image-imports/${task.id}`);
    } finally {
      locked(false); if(selected) draw(selected);
      el('errors').textContent=messages.slice(0,100).join('\n')+(messages.length>100?`\n另有${messages.length-100}项，请按任务逐页重试。`:'');
      // 只刷新素材列表，不重置当前任务/已选文件，使失败重试仍使用同一任务。
      await refreshVideos();
      await refresh({preserve:true});
    }
  }
  el('start').onclick=safe(async()=>{
    if(!project() || !files.length) throw Error('请选择产品和多张图片/文件夹');
    if(!el('group').value.trim()) throw Error('请填写拍摄来源组；未知来源先归入同一组');
    const body={project_id:project(),name:el('name').value.trim(),frame_set_id:el('target').value||null,
      client_key:crypto.randomUUID(),files:files.map(file=>({...fileInfo(file),source_group:el('group').value.trim(),split:el('split').value}))};
    // 防止创建请求未结束时重复点击建立并行任务。
    // 创建请求尚未返回时selected仍可能是上一个任务，禁止误取消旧任务。
    locked(true,{allowCancel:false});
    try {selected=await apiPost('/api/image-imports',body);} finally {locked(false);}
    await uploadTask(selected);
  });
  el('resume').onclick=safe(async()=>{
    if(!selected) throw Error('请选择要恢复的任务');
    await uploadTask(await apiGet(`/api/image-imports/${selected.id}`));
  });
  el('cancel').onclick=safe(async()=>{
    if(!selected) return;
    // 先持久取消，再中止网络；提交期间的服务端也重新校验任务状态。
    selected=await apiPost(`/api/image-imports/${selected.id}/cancel`,{});
    running=false; controllers.forEach(controller=>controller.abort()); draw(selected);
  });
  document.getElementById('active-project').addEventListener('change',safe(refresh));
  window.addEventListener('beforeunload',event=>{if(running){event.preventDefault();event.returnValue='';}});
  safe(async()=>{limits=await apiGet('/api/image-imports/limits'); await refresh();})();
})();
