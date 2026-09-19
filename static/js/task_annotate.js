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
  const canLeave = () => (!dirty && !polygon.length) || window.confirm("当前标注尚未保存，放弃编辑并切换？");
  const selectOptions = (target, rows, label) => fillSelect(el(target), rows, row => row.id, label);
  const endpoint = () => `/api/annotation-sets/${spec.id}/frames/${annotation.frame_id}`;
  const snapshot = () => ({objects: structuredClone(objects), mask: mask?.slice(), selected});
  function restore(value) { objects = value.objects; mask = value.mask; selected = value.selected; dirty = true; polygon = []; redraw(); }
  function checkpoint() {
    undo.push(snapshot()); redo = [];
    // 大图减少历史长度，避免20份全图类别数组占满浏览器内存。
    const limit = Math.max(1, Math.min(20, Math.floor(64 * 1024 * 1024 / Math.max(1, mask?.length || JSON.stringify(objects).length * 2))));
    if (undo.length > limit) undo.splice(0, undo.length - limit);
    dirty = true;
  }
  function reset() {
    generation++; annotation = picture = mask = null; objects = []; undo = []; redo = []; polygon = []; selected = -1; dirty = false;
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
  }
  async function loadFrame() {
    reset(); if (!spec || !el("frame").value) return;
    const token = generation, result = await apiGet(`/api/annotation-sets/${spec.id}/frames/${el("frame").value}`);
    const image = new Image(); image.src = `/api/frames/${result.frame_id}/image`; await image.decode();
    if (token !== generation) return;
    annotation = result; picture = image; objects = result.objects;
    if (result.mask_rle) {
      mask = new Uint8Array(result.width * result.height); let offset = 0;
      for (let i = 0; i < result.mask_rle.length; i += 2) { mask.fill(result.mask_rle[i], offset, offset + result.mask_rle[i + 1]); offset += result.mask_rle[i + 1]; }
    }
    canvas.width = result.width; canvas.height = result.height; el("empty").hidden = true; fit(); redraw();
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
    reset(); sets = []; spec = null; el("frame").replaceChildren();
    if (!el("project").value) return;
    const project = encodeURIComponent(el("project").value);
    const [setRows, frames, focus] = await Promise.all([apiGet(`/api/annotation-sets?project_id=${project}`), apiGet(`/api/frame-sets?project_id=${project}`), apiGet(`/api/focus-regions?project_id=${project}`)]);
    sets = setRows; selectOptions("set", sets, row => `${row.name} · ${names[row.task_type]}`);
    selectOptions("frameset", frames, row => row.name); fillSelect(el("focus"), focus, row => row.id, row => row.name, "原图完整范围"); configure();
  }
  // 切换失败/取消时恢复选择，避免下拉框与仍在编辑的帧不一致。
  ["project", "set", "frameset", "frame"].forEach(key => {
    el(key).addEventListener("focus", () => { el(key).dataset.previous = el(key).value; });
    el(key).onchange = attempt(async () => {
      if (busy || !canLeave()) { el(key).value = el(key).dataset.previous || ""; return; }
      if (key === "project") await loadProject();
      else if (key === "set") { configure(); await loadFrame(); }
      else if (key === "frameset") { reset(); selectOptions("frame", el(key).value ? await apiGet(`/api/frame-sets/${el(key).value}/frames`) : [], row => `${row.frame_index ?? row.id} · ${row.width}×${row.height}`); }
      else await loadFrame();
      el(key).dataset.previous = el(key).value;
    });
  });
  el("create").onsubmit = attempt(async event => {
    event.preventDefault(); if (!el("project").value) throw Error("请先选择项目"); if (!canLeave()) return;
    const created = await apiPost("/api/annotation-sets", {project_id: el("project").value, name: el("name").value, task_type: el("task").value});
    sets.push(created); selectOptions("set", sets, row => `${row.name} · ${names[row.task_type]}`); el("set").value = created.id; configure(); await loadFrame();
  });
  const importPayload = () => ({project_id:el("project").value,name:el("import-name").value,task_type:el("import-task").value,source_dir:el("import-path").value.trim()});
  el("inspect").onclick = attempt(async () => {
    if(!el("project").value) throw Error("请先选择项目");
    const result=await apiPost("/api/task-datasets/inspect",importPayload());
    el("import-status").textContent=`预检通过：${names[result.task_type]}，${result.frame_count}张，标签${result.label_codes.join("、")}；原目录不修改。`;
  });
  el("import").onsubmit = attempt(async event => {
    event.preventDefault(); if(!el("project").value) throw Error("请先选择项目"); if(!canLeave()) return;
    el("import").inert=true;
    try {
      const result=await apiPost("/api/task-datasets/import",importPayload());
      await loadProject(); el("set").value=result.annotation_set.id; configure(); el("frameset").value=result.frame_set_id;
      selectOptions("frame",await apiGet(`/api/frame-sets/${result.frame_set_id}/frames`),row=>`${row.frame_index} · ${row.width}×${row.height}`);
      el("import-status").textContent=`导入完成：${result.frame_count}张，请选择图片编辑或直接导出训练版本。`;
    } finally {el("import").inert=false;}
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
    if (!annotation || busy || event.button !== 0) return; event.preventDefault(); canvas.focus(); canvas.setPointerCapture(event.pointerId);
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
      if (b[0]===b[2] || b[1]===b[3]) { objects.splice(selected,1); selected=-1; }
    }
    drag=null; redraw();
  }
  canvas.onpointerup = endDrag; canvas.onpointercancel = endDrag;
  el("finish").onclick = attempt(() => {
    if (polygon.length < 3) throw Error("请至少绘制3个顶点"); checkpoint();
    if (mask) {
      const raster=document.createElement("canvas"); raster.width=canvas.width; raster.height=canvas.height;
      const rc=raster.getContext("2d"); rc.beginPath(); polygon.forEach((p,i)=>rc[i?"lineTo":"moveTo"](p[0]*canvas.width,p[1]*canvas.height)); rc.closePath(); rc.fill();
      const pixels=rc.getImageData(0,0,canvas.width,canvas.height).data, value=spec.label_codes.indexOf(el("label").value)+1;
      for(let i=0;i<mask.length;i++) if(pixels[i*4+3]>=128) mask[i]=value;
    } else if(fragment && selected>=0) objects[selected].polygons.push(polygon);
    else { objects.push({instance_id:crypto.randomUUID(),label_code:el("label").value,polygons:[polygon]}); selected=objects.length-1; }
    polygon=[]; fragment=false; redraw();
  });
  el("fragment").onclick = attempt(() => { if(selected<0) throw Error("请先选中实例"); fragment=true; polygon=[]; el("tool").value="polygon"; status("正在给选中实例添加片段；Enter 完成"); });
  el("delete").onclick = () => { if(selected>=0) { checkpoint(); objects.splice(selected,1); selected=-1; redraw(); } };
  el("undo").onclick = () => { if(undo.length) { redo.push(snapshot()); restore(undo.pop()); } };
  el("redo").onclick = () => { if(redo.length) { undo.push(snapshot()); restore(redo.pop()); } };
  el("fit").onclick = () => { fit(); redraw(); };
  el("zoom").oninput = () => { const old=scale; scale=Number(el("zoom").value)/100; offset=offset.map((value,i)=>(i?viewport.clientHeight:viewport.clientWidth)/2+ (value-(i?viewport.clientHeight:viewport.clientWidth)/2)*scale/old); transform(); redraw(); };
  el("tool").onchange = () => { polygon=[]; fragment=false; redraw(); };
  el("save").onclick = attempt(async () => {
    if(!annotation || busy) return; if(polygon.length) throw Error("请先完成或取消正在绘制的多边形");
    const payload={revision:annotation.revision};
    if(mask) { const runs=[]; let start=0; for(let i=1;i<=mask.length;i++) if(i===mask.length || mask[i]!==mask[start]) { runs.push(mask[start],i-start); start=i; } payload.mask_rle=runs; }
    else payload.objects=objects;
    busy=true; document.querySelector("main").inert=true;
    try { const saved=await parseApiResponse(await fetch(endpoint(),{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)})); annotation.revision=saved.revision; dirty=false; redraw(); showToast("标注已保存"); } finally {busy=false; document.querySelector("main").inert=false;}
  });
  el("export").onclick = attempt(async () => {
    if(!spec) throw Error("请选择标注集"); if(dirty || polygon.length) throw Error("请先保存当前编辑，再导出标注集");
    el("export").disabled=true;
    try { const result=await apiPost(`/api/annotation-sets/${spec.id}/export`,{name:spec.name,focus_region_id:el("focus").value||null}); status(`数据集已生成：${result.name}（${result.id}），可进入模型训练`); } finally {el("export").disabled=false;}
  });
  canvas.onkeydown = event => { if(event.key==="Enter") {event.preventDefault(); el("finish").click();} if(event.key==="Escape") {polygon=[];fragment=false;redraw();} if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==="z") {event.preventDefault();el(event.shiftKey?"redo":"undo").click();} };
  window.addEventListener("beforeunload",event=>{if(dirty||polygon.length){event.preventDefault();event.returnValue="";}});
  attempt(async()=>{selectOptions("project",await apiGet("/api/projects"),row=>row.name);configure();})();
})();
