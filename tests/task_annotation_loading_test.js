// 执行实际选择器事件代码；请求未完成不能切帧，失败也必须释放界面。
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const source = fs.readFileSync(path.join(__dirname,"../static/js/task_annotate.js"),"utf8");
const lock = source.slice(source.indexOf("  function lockEditor("),source.indexOf("  const selectOptions"));
const events = source.slice(source.indexOf('  ["project", "set", "frameset", "frame"].forEach'),source.indexOf('  el("create").onsubmit'));
const elements = new Map(["project","set","frameset","frame"].map(key=>[key,{value:"selected",dataset:{previous:"previous"},addEventListener(){}}]));
const main = {inert:false};
let complete;
const request = new Promise(resolve=>{complete=resolve;});
const script = new Function("document","el","apiGet","selectOptions","attempt","canLeave","reset","loadFrame","loadProject","configure",'let busy=false;'+lock+events);
script({querySelector:()=>main},key=>elements.get(key),()=>request,()=>{},fn=>fn,()=>true,()=>{},async()=>{},async()=>{},()=>{});
(async()=>{
    const pending=elements.get("frameset").onchange();
    assert(main.inert);
    for(const item of elements.values()) assert(item.disabled);
    complete([]); await pending;
    assert(!main.inert);
    for(const item of elements.values()) assert(!item.disabled);
    console.log("task annotation loading serialization passed");
})().catch(error=>{console.error(error);process.exitCode=1;});
