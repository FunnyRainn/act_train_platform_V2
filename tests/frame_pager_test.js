const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const scope={window:{}};vm.runInNewContext(fs.readFileSync('static/js/frame_pager.js','utf8'),scope);
(async()=>{
  const pending=[];
  const pager=new scope.window.FramePager((frameSet,offset)=>new Promise(resolve=>pending.push({frameSet,offset,resolve})));
  pager.reset('frames');
  const old=pager.prepare(0), recent=pager.prepare(1499);
  const items=Array.from({length:100},(_,i)=>({id:`f${1400+i}`}));
  pending[1].resolve({items,offset:1400,total:3000});
  assert.equal(pager.commit(await recent),true);assert.equal(pager.index,1499);
  pending[0].resolve({items:[{id:'old'}],offset:0,total:3000});
  assert.equal(await old,null);assert.equal(pager.index,1499);
  const last=pager.prepare(2999);pending[2].resolve({items:Array.from({length:100},(_,i)=>({id:`f${2900+i}`})),offset:2900,total:3000});
  assert.equal(pager.commit(await last),true);assert.equal(pager.page.items.length,100);assert.equal(pager.index,2999);
  const stale=pager.prepare(0);pager.reset('different');pending[3].resolve({items:[],offset:0,total:0});
  assert.equal(await stale,null);assert.equal(pager.total,0);
  console.log('frame pager: first/middle/last and stale generations passed');
})();
