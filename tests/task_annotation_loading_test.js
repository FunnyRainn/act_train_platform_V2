// 执行实际选择器事件代码；请求未完成不能切帧，失败也必须释放界面。
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const source = fs.readFileSync(path.join(__dirname,"../static/js/task_annotate.js"),"utf8");
const lock = source.slice(source.indexOf("  function lockEditor("),source.indexOf("  const selectOptions"));
const start = source.indexOf('  ["project", "set", "frameset"].forEach');
assert(start >= 0, '必须执行当前实际选择器事件，不能因切片标记过期而空跑');
const events = source.slice(start,source.indexOf('  el("create").onsubmit'));
async function scenario(fail) {
    const elements = new Map(["project","set","frameset","frame"].map(key=>[key,{value:"selected",disabled:false}]));
    const main = {inert:false};
    let complete, reject;
    const request = new Promise((resolve, fail)=>{complete=resolve;reject=fail;});
    const script = new Function("document","el","attempt","canLeave","loadProject","configure","pager","go","reset","navigation",
      'let busy=false;const selection={project:"previous",set:"previous",frameset:"previous"};'+lock+events);
    script({querySelector:()=>main},key=>elements.get(key),fn=>fn,()=>true,()=>request,()=>{},
      {frameSet:'old',total:3000,index:1499,page:{}},async()=>{},()=>{},()=>{});
    const pending=elements.get("project").onchange();
    await Promise.resolve();
    assert(main.inert);
    for(const item of elements.values()) assert(item.disabled);
    if (fail) {
      reject(Error('请求失败'));await assert.rejects(pending,/请求失败/);
      assert.equal(elements.get('project').value,'previous');
    } else {complete([]); await pending;}
    assert(!main.inert);
    for(const item of elements.values()) assert(!item.disabled);
}
(async()=>{await scenario(false);await scenario(true);console.log("task annotation loading: success/failure locking and selection restore passed");})()
  .catch(error=>{console.error(error);process.exitCode=1;});
