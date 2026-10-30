/* 三任务共用坐标与编辑历史；原始mask只在显式保存时传输，不混用显示颜色。 */
(() => {
  "use strict";
  const el = id => document.getElementById(`ta-${id}`);
  const canvas = el("canvas"), ctx = canvas.getContext("2d"), viewport = el("viewport");
  const names = {detect:"目标检测", instance_segment:"实例分割", semantic_segment:"语义分割"};
  let sets = [], spec = null, annotation = null, picture = null, mask = null;
  let objects = [], selected = -1, polygon = [], fragment = false, dirty = false;
  let undo = [], redo = [], scale = 1, offset = [0, 0], drag = null, busy = false, generation = 0;
  const colors = ["#55d6ff", "#ffc857", "#ee8fdf", "#64e49b", "#ff8d75"];
  const color = code => colors[Math.max(0, spec.label_codes.indexOf(code)) % colors.length];
  const status = text => { el("status").textContent = text; el("status").dataset.dirty = String(dirty); };
  const attempt = fn => async event => { try { await fn(event); } catch (error) { status(error.message); showToast(error.message, "error"); } };
  let saveTimer=null, saving=null;
  const pager=new window.FramePager((frameSet,offset,frameId)=>apiGet(`/api/frame-sets/${encodeURIComponent(frameSet)}/frames-page?offset=${offset}&frame_id=${encodeURIComponent(frameId)}`));
  const selection={project:'',set:'',frameset:''};
  async function canLeave() {
    if(polygon.length) {
      const choice=await new Promise(resolve=>{
        const dialog=el('polygon-dialog');
        const finish=value=>{dialog.close();resolve(value);};
        el('polygon-finish').onclick=()=>finish('finish');
        el('polygon-discard').onclick=()=>finish('discard');
        el('polygon-cancel').onclick=()=>finish('cancel');
        dialog.oncancel=event=>{event.preventDefault();finish('cancel');};
        dialog.showModal(); el('polygon-cancel').focus();
      });
      if(choice==='cancel') return false;
      if(choice==='finish') finishPolygon(); else {polygon=[];fragment=false;redraw();}
    }
    if(saving) await saving;
    if(dirty) await saveCurrent();
    return true;
  }
  function lockEditor(locked) {
    // 列表/图片请求完成前禁止再次切换；旧帧列表不能在新图片加载后反向清空选择。
    busy = locked; document.querySelector("main").inert = locked;
    for (const key of ["project","set","frameset","frame"]) el(key).disabled = locked;
  }
  const selectOptions = (target, rows, label) => fillSelect(el(target), rows, row => row.id, label);
  const endpoint = () => `/api/annotation-sets/${spec.id}/frames/${annotation.frame_id}`;
  const snapshot = () => ({objects: structuredClone(objects), mask: mask?.slice(), selected, dirty});
  function restore(value) { objects = value.objects; mask = value.mask; selected = value.selected; dirty = true; polygon = []; redraw(); }
  function checkpoint() {
    undo.push(snapshot()); redo = [];
    // 大图减少历史长度，避免20份全图类别数组占满浏览器内存。
    const limit = Math.max(1, Math.min(20, Math.floor(64 * 1024 * 1024 / Math.max(1, mask?.length || JSON.stringify(objects).length * 2))));
    if (undo.length > limit) undo.splice(0, undo.length - limit);
    dirty = true;
  }
  function reset() {
    clearTimeout(saveTimer);
    generation++; annotation = picture = mask = null; objects = []; undo = []; redo = []; polygon = []; selected = -1; dirty = false; drag = null; fragment = false;
    canvas.width = canvas.height = 1; el("empty").hidden = false; el("instances").replaceChildren(); status("请选择标注集和图片");
  }
  function position(event) {
    const box = canvas.getBoundingClientRect();
    return [Math.max(0, Math.min(1, (event.clientX - box.left) / box.width)), Math.max(0, Math.min(1, (event.clientY - box.top) / box.height))];
  }
  function transform() { canvas.style.transform = `translate(${offset[0]}px,${offset[1]}px) scale(${scale})`; }
  function fit() {
    if (!annotation) return;
    scale = Math.min(viewport.clientWidth / canvas.width, viewport.clientHeight / canvas.height) * .94;
    offset = [(viewport.clientWidth - canvas.width * scale) / 2, (viewport.clientHeight - canvas.height * scale) / 2]; transform();
    el("zoom").value = Math.round(scale * 100);
  }
  function path(points) { ctx.beginPath(); points.forEach((p, i) => ctx[i ? "lineTo" : "moveTo"](p[0] * canvas.width, p[1] * canvas.height)); }
  function redraw() {
    if (!picture) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height); ctx.drawImage(picture, 0, 0);
    if (mask) {
      const overlay = new ImageData(canvas.width, canvas.height);
      for (let i = 0; i < mask.length; i++) {
        const value = mask[i], hex = value === 255 ? "#8c929b" : value === 0 ? "#101820" : colors[(value - 1) % colors.length];
        const rgb = parseInt(hex.slice(1), 16), j = i * 4;
        overlay.data[j] = rgb >> 16; overlay.data[j + 1] = (rgb >> 8) & 255; overlay.data[j + 2] = rgb & 255; overlay.data[j + 3] = value === 255 ? 70 : 105;
      }
      const layer = document.createElement("canvas"); layer.width = canvas.width; layer.height = canvas.height;
      layer.getContext("2d").putImageData(overlay, 0, 0); ctx.drawImage(layer, 0, 0);
    }
    ctx.lineWidth = Math.max(1, 2 / scale);
    objects.forEach((object, index) => {
      ctx.strokeStyle = color(object.label_code); ctx.fillStyle = ctx.strokeStyle + "33";
      const fragments = object.bbox ? [[[object.bbox[0], object.bbox[1]], [object.bbox[2], object.bbox[1]], [object.bbox[2], object.bbox[3]], [object.bbox[0], object.bbox[3]]]] : object.polygons;
      fragments.forEach(points => {
        path(points); ctx.closePath(); ctx.fill(); ctx.stroke();
        if (index === selected) points.forEach(p => { ctx.fillStyle = "#fff"; ctx.fillRect(p[0] * canvas.width - 3 / scale, p[1] * canvas.height - 3 / scale, 6 / scale, 6 / scale); });
      });
    });
    if (polygon.length) { ctx.strokeStyle = "#fff"; path(polygon); ctx.stroke(); polygon.forEach(p => { ctx.fillStyle = "#fff"; ctx.fillRect(p[0]*canvas.width-2/scale, p[1]*canvas.height-2/scale, 4/scale, 4/scale); }); }
    el("instances").replaceChildren(...objects.map((object, index) => {
      const button = document.createElement("button"); button.type = "button"; button.className = index === selected ? "selected" : "";
      button.textContent = `${index + 1}. ${object.label_code}${object.polygons ? ` · ${object.polygons.length}片段` : ""}`;
      button.onclick = () => { selected = index; redraw(); }; return button;
    }));
    el("undo").disabled = !undo.length; el("redo").disabled = !redo.length;
    status(`${names[spec.task_type]} · ${annotation.width}×${annotation.height} · 修订${annotation.revision} · ${dirty ? "未保存" : "已载入"}`);
    clearTimeout(saveTimer);
    if(dirty && !drag && !polygon.length && !busy && !saving) saveTimer=setTimeout(()=>{
      saveCurrent().catch(error=>{status(`自动保存失败，编辑已保留：${error.message}`);});
    },450);
  }
  async function loadFrame(frameId=el('frame').value) {
    if (!spec || !frameId) return;
    // 新图片/标注完整到达前保留旧画面，失败不能清空未保存编辑或错写另一帧。
    const token = ++generation, specId=spec.id, result = await apiGet(`/api/annotation-sets/${specId}/frames/${frameId}`);
    const image = new Image(); image.src = `/api/frames/${result.frame_id}/image`; await image.decode();
    if (token !== generation || spec?.id!==specId) return;
    clearTimeout(saveTimer); mask=null; undo=[];redo=[];polygon=[];selected=-1;dirty=false;drag=null;fragment=false;
    annotation = result; picture = image; objects = result.objects;
    if (result.mask_rle) {
      mask = new Uint8Array(result.width * result.height); let offset = 0;
      for (let i = 0; i < result.mask_rle.length; i += 2) { mask.fill(result.mask_rle[i], offset, offset + result.mask_rle[i + 1]); offset += result.mask_rle[i + 1]; }
    }
    canvas.width = result.width; canvas.height = result.height; el("empty").hidden = true; fit(); redraw();
    try {localStorage.setItem(`train-frame-${spec.id}-${el('frameset').value}`,result.frame_id);} catch(_error) {}
  }
  function navigation() {
    el('ordinal').value=Math.max(1,pager.index+1);el('ordinal').max=Math.max(1,pager.total);
    el('progress').max=Math.max(1,pager.total);el('progress').value=Math.max(1,pager.index+1);
    const frame=pager.page?.items[pager.index-pager.page.offset];
    el('frame-info').textContent=`${pager.total?pager.index+1:0} / ${pager.total}${frame?` · ${frame.original_name || `原始帧号 ${frame.frame_index}`}`:''}`;
    el('prev').disabled=pager.index<=0;el('next').disabled=pager.index+1>=pager.total;
    el('legacy').href=`/annotate?frame_set_id=${encodeURIComponent(el('frameset').value)}`;
  }
  async function go(index,restore=false) {
    if(!Number.isInteger(index) || index<0 || (!restore && pager.total && index>=pager.total)) {navigation();throw Error('序号超出当前帧集范围');}
    if(busy || !await canLeave()) {navigation();return;}
    lockEditor(true);
    try {
      let remembered='';
      if(restore && spec) try {remembered=localStorage.getItem(`train-frame-${spec.id}-${el('frameset').value}`)||'';} catch(_error) {}
      let candidate;
      try {candidate=await pager.prepare(index,remembered);} catch(error) {
        if(!remembered) throw error; candidate=await pager.prepare(index);
      }
      if(!candidate) return;
      if(candidate.frame) await loadFrame(candidate.frame.id); else reset();
      if(pager.commit(candidate)) {
        selectOptions('frame',candidate.frame?[candidate.frame]:[],row=>row.id);
        if(candidate.frame) el('frame').value=candidate.frame.id;
      }
    } finally {lockEditor(false);navigation();}
  }
  function configure() {
    spec = sets.find(row => row.id === el("set").value) || null;
    const task = spec?.task_type;
    const tools = task === "semantic_segment" ? [["brush", "类别画笔"], ["polygon", "类别多边形填充"], ["background", "背景画笔（0）"], ["erase", "橡皮／忽略（255）"], ["pan", "平移"]] : [["select", "选择／顶点编辑"], [task === "detect" ? "box" : "polygon", task === "detect" ? "矩形框" : "多边形"], ["pan", "平移"]];
    el("tool").innerHTML = tools.map(([value, name]) => `<option value="${value}">${name}</option>`).join("");
    el("label").innerHTML = (spec?.label_codes || []).map(code => `<option value="${esc(code)}">${esc(code)}</option>`).join("");
    el("fragment").hidden = task !== "instance_segment"; el("delete").hidden = task === "semantic_segment"; el("brush").disabled = task !== "semantic_segment";
  }
  async function loadProject() {
    reset(); sets = []; spec = null; el("frame").replaceChildren(); pager.reset('');navigation();
    if (!el("project").value) return;
    const project = encodeURIComponent(el("project").value);
    const [setRows, frames, focus] = await Promise.all([apiGet(`/api/annotation-sets?project_id=${project}`), apiGet(`/api/frame-sets?project_id=${project}`), apiGet(`/api/focus-regions?project_id=${project}`)]);
    sets = setRows; selectOptions("set", sets, row => `${row.name} · ${names[row.task_type]}`);
    selectOptions("frameset", frames, row => row.name); fillSelect(el("focus"), focus, row => row.id, row => row.name, "原图完整范围"); configure();
  }
  // 切换失败/取消时恢复选择，避免下拉框与仍在编辑的帧不一致。
  ["project", "set", "frameset"].forEach(key => {
    el(key).onchange = attempt(async () => {
      const next=el(key).value; el(key).value=selection[key];
      if (busy || !await canLeave()) return;
      el(key).value=next;
      try {
        if (key === "project") {lockEditor(true);await loadProject();}
        else if (key === "set") {configure(); if(spec) await go(Math.max(0,pager.index),true);else reset();}
        else {pager.reset(next);if(next) await go(0,true);else {reset();navigation();}}
        for(const field of Object.keys(selection)) selection[field]=el(field).value;
      } catch(error) {el(key).value=selection[key];configure();throw error;}
      finally { lockEditor(false); }
    });
  });
  el("create").onsubmit = attempt(async event => {
    event.preventDefault(); if (!el("project").value) throw Error("请先选择项目"); if (!await canLeave()) return;
    lockEditor(true);
    try {
      const created = await apiPost("/api/annotation-sets", {project_id: el("project").value, name: el("name").value, task_type: el("task").value});
      sets.push(created); selectOptions("set", sets, row => `${row.name} · ${names[row.task_type]}`); el("set").value = created.id; selection.set=created.id; configure(); await loadFrame();
    } finally { lockEditor(false); }
  });
  const importPayload = () => ({project_id:el("project").value,name:el("import-name").value,task_type:el("import-task").value,source_dir:el("import-path").value.trim()});
  el("inspect").onclick = attempt(async () => {
    if(!el("project").value) throw Error("请先选择项目");
    const result=await apiPost("/api/task-datasets/inspect",importPayload());
    el("import-status").textContent=`预检通过：${names[result.task_type]}，${result.frame_count}张，标签${result.label_codes.join("、")}；原目录不修改。`;
  });
  el("import").onsubmit = attempt(async event => {
    event.preventDefault(); if(!el("project").value) throw Error("请先选择项目"); if(!await canLeave()) return;
    lockEditor(true);
    try {
      const result=await apiPost("/api/task-datasets/import",importPayload());
      await loadProject(); el("set").value=result.annotation_set.id; configure(); el("frameset").value=result.frame_set_id;
      for(const field of Object.keys(selection)) selection[field]=el(field).value;
      pager.reset(result.frame_set_id);lockEditor(false);await go(0);
      el("import-status").textContent=`导入完成：${result.frame_count}张，请选择图片编辑或直接导出训练版本。`;
    } finally {lockEditor(false);}
  });
  function paint(p, previous = p) {
    const radius = Math.max(1, Math.min(256, Number(el("brush").value) || 12)) / 2;
    const value = el("tool").value === "erase" ? 255 : el("tool").value === "background" ? 0 : spec.label_codes.indexOf(el("label").value) + 1;
    const distance = Math.hypot((p[0] - previous[0]) * canvas.width, (p[1] - previous[1]) * canvas.height), steps = Math.max(1, Math.ceil(distance / Math.max(1, radius / 2)));
    for (let step = 0; step <= steps; step++) {
      const x = (previous[0] + (p[0] - previous[0]) * step / steps) * canvas.width, y = (previous[1] + (p[1] - previous[1]) * step / steps) * canvas.height;
      for (let py = Math.max(0, Math.floor(y - radius)); py < Math.min(canvas.height, y + radius); py++) for (let px = Math.max(0, Math.floor(x - radius)); px < Math.min(canvas.width, x + radius); px++) if ((px+.5-x)**2 + (py+.5-y)**2 <= radius**2) mask[py * canvas.width + px] = value;
    }
  }
  canvas.onpointerdown = event => {
    // 获得快捷键焦点时不能让浏览器滚动画布，否则首个顶点会用变化后的矩形算坐标。
    if (!annotation || busy || event.button !== 0) return; event.preventDefault(); canvas.focus({preventScroll:true}); canvas.setPointerCapture(event.pointerId);
    const p = position(event), tool = el("tool").value;
    if (tool === "pan") { drag = {type:"pan", start:[event.clientX, event.clientY], offset:[...offset]}; return; }
    if (tool === "polygon") { polygon.push(p); redraw(); return; }
    if (mask) { checkpoint(); paint(p); drag = {type:"paint", previous:p}; redraw(); return; }
    if (tool === "box") { checkpoint(); objects.push({instance_id:crypto.randomUUID(), label_code:el("label").value, bbox:[...p, ...p]}); selected = objects.length - 1; drag = {type:"box", start:p}; }
    if (tool === "select") {
      // 顶点命中优先；点击内部可选中实例，不生成隐含跟踪身份。
      let hit = null;
      objects.forEach((object, i) => (object.polygons || [[[object.bbox[0], object.bbox[1]], [object.bbox[2], object.bbox[3]]]]).forEach((points, f) => points.forEach((v, j) => { if (Math.hypot((v[0]-p[0])*canvas.width*scale, (v[1]-p[1])*canvas.height*scale) < 10) hit = {i, f, j}; })));
      if (hit) { checkpoint(); selected = hit.i; drag = {type:"vertex", ...hit}; }
      else {
        selected = -1;
        objects.forEach((object, i) => {
          if (object.bbox) { const [x0,y0,x1,y1] = object.bbox; if (p[0]>=x0 && p[0]<=x1 && p[1]>=y0 && p[1]<=y1) selected = i; }
          else object.polygons.forEach(points => { path(points); ctx.closePath(); if (ctx.isPointInPath(p[0]*canvas.width,p[1]*canvas.height)) selected=i; });
        });
      }
    }
    redraw();
  };
  canvas.onpointermove = event => {
    if (!drag) return; const p = position(event);
    if (drag.type === "pan") { offset = [drag.offset[0]+event.clientX-drag.start[0], drag.offset[1]+event.clientY-drag.start[1]]; transform(); return; }
    if (drag.type === "paint") { paint(p, drag.previous); drag.previous = p; }
    if (drag.type === "box") objects[selected].bbox = [Math.min(p[0],drag.start[0]),Math.min(p[1],drag.start[1]),Math.max(p[0],drag.start[0]),Math.max(p[1],drag.start[1])];
    if (drag.type === "vertex") {
      const object = objects[drag.i];
      if (object.polygons) object.polygons[drag.f][drag.j] = p;
      else { const box=object.bbox, index=drag.j*2; box[index]=p[0]; box[index+1]=p[1]; }
    }
    redraw();
  };
  function endDrag() {
    if (drag && ["box","vertex"].includes(drag.type) && objects[selected]?.bbox) {
      const b=objects[selected].bbox; objects[selected].bbox=[Math.min(b[0],b[2]),Math.min(b[1],b[3]),Math.max(b[0],b[2]),Math.max(b[1],b[3])];
      if (b[0]===b[2] || b[1]===b[3]) {
        // 无效点击/退化框不应产生一条“明确无目标”的自动保存。
        const previous=undo.pop(); if(previous) {objects=previous.objects;mask=previous.mask;selected=previous.selected;dirty=previous.dirty;}
      }
    }
    drag=null; redraw();
  }
  canvas.onpointerup = endDrag; canvas.onpointercancel = endDrag;
  function finishPolygon() {
    if (polygon.length < 3) throw Error("请至少绘制3个顶点"); checkpoint();
    if (mask) {
      const raster=document.createElement("canvas"); raster.width=canvas.width; raster.height=canvas.height;
      const rc=raster.getContext("2d"); rc.beginPath(); polygon.forEach((p,i)=>rc[i?"lineTo":"moveTo"](p[0]*canvas.width,p[1]*canvas.height)); rc.closePath(); rc.fill();
      const pixels=rc.getImageData(0,0,canvas.width,canvas.height).data, value=spec.label_codes.indexOf(el("label").value)+1;
      for(let i=0;i<mask.length;i++) if(pixels[i*4+3]>=128) mask[i]=value;
    } else if(fragment && selected>=0) objects[selected].polygons.push(polygon);
    else { objects.push({instance_id:crypto.randomUUID(),label_code:el("label").value,polygons:[polygon]}); selected=objects.length-1; }
    polygon=[]; fragment=false; redraw();
  }
  el("finish").onclick = attempt(finishPolygon);
  el("fragment").onclick = attempt(() => { if(selected<0) throw Error("请先选中实例"); fragment=true; polygon=[]; el("tool").value="polygon"; status("正在给选中实例添加片段；Enter 完成"); });
  el("delete").onclick = () => { if(selected>=0) { checkpoint(); objects.splice(selected,1); selected=-1; redraw(); } };
  el("undo").onclick = () => { if(undo.length) { redo.push(snapshot()); restore(undo.pop()); } };
  el("redo").onclick = () => { if(redo.length) { undo.push(snapshot()); restore(redo.pop()); } };
  el("fit").onclick = () => { fit(); redraw(); };
  el("zoom").oninput = () => { const old=scale; scale=Number(el("zoom").value)/100; offset=offset.map((value,i)=>(i?viewport.clientHeight:viewport.clientWidth)/2+ (value-(i?viewport.clientHeight:viewport.clientWidth)/2)*scale/old); transform(); redraw(); };
  el("tool").onchange = attempt(async () => {if(polygon.length && !await canLeave()) el('tool').value='polygon'; redraw();});
  async function saveCurrent(explicit=false) {
    if(saving) return saving;
    clearTimeout(saveTimer);
    if(!annotation || (!dirty && !explicit)) return;
    if(polygon.length || drag) throw Error("请先完成正在绘制的轮廓");
    const payload={revision:annotation.revision};
    if(mask) { const runs=[]; let start=0; for(let i=1;i<=mask.length;i++) if(i===mask.length || mask[i]!==mask[start]) { runs.push(mask[start],i-start); start=i; } payload.mask_rle=runs; }
    else payload.objects=objects;
    const token=generation, frameId=annotation.frame_id, specId=spec.id, url=endpoint();
    lockEditor(true);
    saving=(async()=>{
      try { const saved=await parseApiResponse(await fetch(url,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)}));
        if(token!==generation || annotation?.frame_id!==frameId || spec?.id!==specId) throw Error('保存回执与当前帧不一致');
        annotation.revision=saved.revision; dirty=false; redraw(); status('标注已保存');
      } finally {lockEditor(false);saving=null;}
    })();
    return saving;
  }
  el("save").onclick = attempt(()=>saveCurrent(true));
  el('prev').onclick=attempt(()=>go(pager.index-1));el('next').onclick=attempt(()=>go(pager.index+1));
  el('go').onclick=attempt(()=>go(Number(el('ordinal').value)-1));
  el('ordinal').onkeydown=attempt(event=>{if(event.key==='Enter'){event.preventDefault();return go(Number(el('ordinal').value)-1);}});
  el('progress').oninput=()=>{el('frame-info').textContent=`准备跳转 ${el('progress').value} / ${pager.total}`;};
  el('progress').onchange=attempt(()=>go(Number(el('progress').value)-1));
  document.addEventListener('keydown',event=>{
    if(event.ctrlKey||event.metaKey||event.altKey||['INPUT','SELECT','TEXTAREA','BUTTON'].includes(event.target.tagName)||el('polygon-dialog').open) return;
    if(['a','d'].includes(event.key.toLowerCase())) {event.preventDefault();attempt(()=>go(pager.index+(event.key.toLowerCase()==='a'?-1:1)))();}
  });
  el("export").onclick = attempt(async () => {
    if(!spec) throw Error("请选择标注集"); if(dirty || polygon.length) throw Error("请先保存当前编辑，再导出标注集");
    el("export").disabled=true;
    try {
      let allow_frame_split=false;
      const url=`/api/annotation-sets/${spec.id}`;
      let preview=await apiPost(`${url}/export-preview`,{allow_frame_split});
      if(preview.requires_choice) {
        if(!confirm(`${preview.warnings.join('\n')}\n\n确认接受仅作内部功能验证的按帧划分？取消后可以补充独立拍摄来源。`)) return;
        allow_frame_split=true;preview=await apiPost(`${url}/export-preview`,{allow_frame_split});
      }
      const summary=`训练 ${preview.counts.train||0} / 验证 ${preview.counts.val||0} / 测试 ${preview.counts.test||0}\n${preview.groups.map(group=>`${group.source}：${group.count}张 → ${group.split}`).join('\n')}\n${preview.warnings.join('\n')}`;
      if(!confirm(`导出划分预览（只包含已保存标注）\n${summary}\n确认生成数据集版本？`)) return;
      const result=await apiPost(`${url}/export`,{name:spec.name,focus_region_id:el("focus").value||null,allow_frame_split,split_preview_hash:preview.preview_hash});
      status(`数据集已生成：${result.name}（${result.id}），可进入模型训练`);
    } finally {el("export").disabled=false;}
  });
  canvas.onkeydown = event => { if(event.key==="Enter") {event.preventDefault(); el("finish").click();} if(event.key==="Escape") {polygon=[];fragment=false;redraw();} if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==="z") {event.preventDefault();el(event.shiftKey?"redo":"undo").click();} };
  window.addEventListener("beforeunload",event=>{if(dirty||polygon.length){event.preventDefault();event.returnValue="";}});
  attempt(async()=>{
    selectOptions("project",await apiGet("/api/projects"),row=>row.name);configure();navigation();
    const query=new URLSearchParams(location.search);
    if(query.get('project_id')) {el('project').value=query.get('project_id');await loadProject();selection.project=el('project').value;}
    if(query.get('frame_set_id')) {el('frameset').value=query.get('frame_set_id');selection.frameset=el('frameset').value;pager.reset(selection.frameset);await go(0,true);}
  })();
})();
