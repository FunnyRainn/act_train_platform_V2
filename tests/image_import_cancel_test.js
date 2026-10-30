/* 创建新任务和旧任务取消的异步交错；运行实际页面脚本，不复制产品实现。 */
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

async function main(){
  const nodes=new Map();
  function node(id){if(!nodes.has(id))nodes.set(id,{value:'',disabled:false,textContent:'',files:[],addEventListener(){}});return nodes.get(id);}
  node('active-project').value='project';
  node('images-name').value='new';node('images-group').value='known-source';
  const item={relative_path:'one.png',size:10,last_modified:20,ordinal:0,state:'pending'};
  const old={id:'old',project_id:'project',counts:{completed:1,pending:1},total:2,done:1,items:[],state:'active'};
  const next={id:'new',project_id:'project',counts:{pending:1},total:1,done:0,items:[item],state:'active'};
  let resolveCreate,fetchStarted=false,posts=[],cancelled=false;
  const deferred=new Promise(resolve=>{resolveCreate=resolve;});
  const context={console,Intl,Map,Set,Promise,AbortController,
    document:{getElementById:node},window:{addEventListener(){}},
    localStorage:{getItem:()=> 'old',setItem(){}},crypto:{randomUUID:()=> 'controlled-key'},
    fillSelect(){},showToast:message=>{throw Error(message);},refreshVideos:async()=>{},
    apiGet:async url=>{
      if(url.endsWith('/limits'))return {extensions:['.png'],files:10000,file_bytes:32*1024**2,page_size:100,parallel_uploads:2};
      if(url.includes('/api/frame-sets?'))return [];
      if(url.includes('/api/image-imports?'))return [next,old];
      if(url.endsWith('/old'))return old;
      if(url.endsWith('/new'))return {...next,state:cancelled?'cancelled':'active'};
      throw Error('unexpected GET '+url);
    },
    apiPost:async(url)=>{
      posts.push(url);
      if(url==='/api/image-imports')return deferred;
      if(url==='/api/image-imports/new/cancel'){cancelled=true;return {...next,state:'cancelled'};}
      throw Error('unexpected POST '+url);
    },
    parseApiResponse:async response=>response,
    fetch:async(_url,options)=>{
      fetchStarted=true;
      return new Promise((_resolve,reject)=>options.signal.addEventListener('abort',()=>{
        const error=new Error('cancelled');error.name='AbortError';reject(error);
      }));
    }};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/js/image_imports.js'),'utf8'),context);
  const tick=()=>new Promise(resolve=>setImmediate(resolve));
  await tick();await tick();
  assert.equal(node('images-cancel').disabled,false,'恢复的持久任务可直接取消，无需重新选择文件');
  node('images-files').files=[{name:'one.png',size:10,lastModified:20}];
  await node('images-files').onchange();
  const creating=node('images-start').onclick();
  await tick();
  assert.equal(node('images-cancel').disabled,true,'新创建请求未完成时不能取消旧任务');
  assert.equal(node('images-start').disabled,true,'创建期间拒绝重复导入');
  resolveCreate(next);await tick();await tick();
  assert.equal(fetchStarted,true);assert.equal(node('images-cancel').disabled,false);
  await node('images-cancel').onclick();await creating;
  assert.deepEqual(posts,['/api/image-imports','/api/image-imports/new/cancel']);
  assert.equal(node('images-start').disabled,false);
  assert.equal(node('images-cancel').disabled,true,'已取消任务不再反复取消');
  assert.match(node('images-status').textContent,/已取消/);
  console.log('image import create/cancel interleaving passed');
}
module.exports=main();
module.exports.catch(error=>{console.error(error);process.exitCode=1;});
