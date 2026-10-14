'use strict';
window.CampRouter=(()=>{
 const stateKey='campGuideNavigation';let listener,listScroll=0,previousFocus=null,position=0,lastHash=location.hash.replace(/^#/,'');
 const hash=()=>location.hash.replace(/^#/,'');
 function parse(value=hash()){
  let parts;try{parts=decodeURIComponent(value).split('/');}catch{return {type:'invalid'};}
  let[type='list',id,index]=parts;if(!type)type='list';if(/^C\d+$/.test(type)){id=type;type='camp';}
  if(!['list','map','camp','weather','season','photos','verified','verified-row'].includes(type))return {type:'invalid'};
  if(['camp','weather','season','photos'].includes(type)&&!/^C\d+$/.test(id||''))return {type:'invalid'};
  if(type==='verified-row'&&!/^\d+$/.test(id||''))return {type:'invalid'};
  return {type,id,index:/^\d+$/.test(index||'')?Number(index):0};
 }
 const url=h=>location.pathname+location.search+(h?'#'+h:'');
 const state=()=>({...history.state,[stateKey]:{position}});
 function navigate(type,id='',index=''){
  const next=type==='list'?'':type==='map'||type==='verified'?type:`${type}/${id}${index!==''?'/'+index:''}`;
  if(next===hash()){listener?.();return;}
  if(parse().type==='list'){listScroll=window.scrollY;previousFocus=document.activeElement;}
  if(type==='photos'&&parse().type==='photos')history.replaceState(state(),'',url(next));
  else{position++;history.pushState(state(),'',url(next));}
  lastHash=next;listener?.();
 }
 function back(){
  if(position>0){history.back();return;}
  const current=parse(),next=['weather','season','photos'].includes(current.type)&&current.id?'camp/'+current.id:'';
  // A refreshed or shared child page has no in-app parent entry. Replace it,
  // so a second return goes to the list instead of revisiting the child.
  position=0;history.replaceState(state(),'',url(next));lastHash=next;listener?.();
 }
 function start(onChange){
  listener=onChange;position=0;history.replaceState(state(),'',url(hash()));
  window.addEventListener('popstate',()=>{position=Number.isInteger(history.state?.[stateKey]?.position)?history.state[stateKey].position:0;lastHash=hash();listener();});
  window.addEventListener('hashchange',()=>{if(hash()===lastHash)return;position++;history.replaceState(state(),'',url(hash()));lastHash=hash();listener();});
 }
 function restoreList(){
  window.scrollTo(0,listScroll);
  if(previousFocus?.isConnected){previousFocus.focus({preventScroll:true});return;}
  for(const key of ['open','album','weather','season','rating']){
   const id=previousFocus?.dataset?.[key];
   if(/^C\d+$/.test(id||'')){document.querySelector('[data-'+key+'="'+id+'"]')?.focus({preventScroll:true});return;}
  }
 }
 return {parse,navigate,back,start,restoreList};
})();
