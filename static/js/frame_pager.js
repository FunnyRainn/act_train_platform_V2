/* 稳定帧 ID / 序号分页：仅缓存当前一页元数据，迟到请求不得更新导航状态。 */
(() => {
  'use strict';
  class FramePager {
    constructor(fetchPage) {this.fetchPage=fetchPage; this.generation=0; this.total=0; this.index=-1; this.frameSet=''; this.page=null;}
    reset(frameSet) {this.generation++; this.frameSet=frameSet; this.total=0; this.index=-1; this.page=null;}
    async prepare(index=0, frameId='') {
      const generation=++this.generation, frameSet=this.frameSet;
      if(!frameSet) return null;
      const offset=Math.floor(Math.max(0,index)/100)*100;
      const page=await this.fetchPage(frameSet,offset,frameId);
      if(generation!==this.generation || frameSet!==this.frameSet) return null;
      const position=page.position ?? Math.min(Math.max(0,index),page.total-1);
      const frame=page.items[position-page.offset];
      if(page.total && !frame) throw Error('帧集发生变化，请刷新后定位');
      return {generation,frameSet,page,frame,index:position};
    }
    commit(candidate) {
      if(!candidate || candidate.generation!==this.generation || candidate.frameSet!==this.frameSet) return false;
      this.page=candidate.page; this.total=candidate.page.total; this.index=candidate.index;
      return true;
    }
  }
  window.FramePager=FramePager;
})();
