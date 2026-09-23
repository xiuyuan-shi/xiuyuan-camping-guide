'use strict';
// A decision aid for self-equipped day camping. Missing evidence never becomes zero.
(function(root){
 const dimensions=[
  {key:'access',name:'到达便利',items:[['parkingWalk','合法停车点至营位步行≤300米'],['publicTransit','公共交通下车后步行≤800米'],['hardPath','停车点至营位有连续硬质步道'],['stepFree','上述通道无必经台阶'],['signedEntrance','营位入口有明确标识']]},
  {key:'facilities',name:'基础设施',items:[['toilet','开放时段内可用厕所≤300米'],['washWater','有可用洗手水源'],['drinkingWater','有明确标识的饮用水或售水点'],['waste','有垃圾收集及清运服务'],['management','有可联系的现场管理人员']]},
  {key:'site',name:'场地条件',items:[['levelPitch','有足够搭建常规帐篷的平整区域'],['shade','有可用树荫或遮阳设施'],['restSeat','有可用休息座椅'],['clean','两次不同日期观察均无明显散落垃圾'],['quiet','两次不同日期观察均无持续施工或扩音干扰']]},
  {key:'dayUse',name:'日营适配',items:[['ownTent','管理方明确允许自带帐篷日营'],['space','管理方划定独立搭建区域'],['separation','活动区与车辆通道有明确分隔'],['hours','开放时间覆盖10至16时'],['booking','入场、预约及收费要求有明确说明']]}
 ];
 const days=(date,now)=>{if(!/^\d{4}-\d{2}-\d{2}$/.test(date||''))return null;const d=new Date(date+'T00:00:00Z');if(!Number.isFinite(+d)||d.toISOString().slice(0,10)!==date)return null;return (+new Date(now+'T00:00:00Z')-d)/86400000;};
 const fresh=(date,now,max)=>{const n=days(date,now);return n!==null&&n>=0&&n<=max;};
 // A provisional, explicitly descriptive index for the existing sheet. It
 // summarizes reported amenities and variety; it never claims verified quality.
 const proxyDimensions=[
  {key:'scenery',name:'已记录的景观类型',patterns:[/湖|水库|江景|溪|河|海|水边|瀑布/,/森林|树林|竹林|树荫|林间/,/草坪|草地|草甸|绿地/,/山景|山谷|峡谷|山顶/,/花海|花田|赏花|樱花|桃花/,/徒步|步道|绿道/]},
  {key:'activities',name:'已记录的活动类型',patterns:[/徒步|骑行/,/桨板|皮划艇|划船|玩水|溯溪/,/烧烤|卡式炉/,/钓鱼|路亚/,/拍照|日落|星空/,/亲子活动|儿童游乐/]}
 ];
 const roundHalf=x=>Math.round(x*2)/2;
 function provisional(record){
  if(record.conflict||record.recommendationAudit?.unresolvedConflict===true)return null;
  const tags=(record.tags||[]).join(' '),parts=[];
  for(const d of proxyDimensions){const matches=d.patterns.filter(p=>p.test(tags));if(matches.length)parts.push({name:d.name,value:Math.min(5,2+matches.length*.6),basis:`${matches.length} 类`});}
  const facts=record.primaryFacts||{},known=['toilet','parking'].filter(k=>['yes','no'].includes(facts[k]?.status));
  if(known.length)parts.push({name:'清单所报基础设施',value:1+4*known.filter(k=>facts[k].status==='yes').length/known.length,basis:known.map(k=>(k==='toilet'?'厕所':'停车')+'：'+(facts[k].status==='yes'?'有':'无')).join('、')});
  if((record.tags||[]).some(t=>/适合亲子|适合老人|适合情侣/.test(t)))parts.push({name:'人群适配线索',value:4,basis:(record.tags||[]).filter(t=>/适合亲子|适合老人|适合情侣/.test(t)).join('、')});
  const route=record.routeSnapshot;
  if(route?.duration>0&&/营位入口|经营营地入口/.test(record.location?.precision||''))parts.push({name:'武林门出发车程',value:route.duration<=1800?5:route.duration<=3600?4:route.duration<=5400?3:route.duration<=7200?2:1,basis:`约${Math.round(route.duration/600)/10}小时`});
  if(parts.length<3)return null;
  const score=parts.reduce((s,p)=>s+p.value,0)/parts.length;
  return {status:'provisional',score,stars:roundHalf(score),parts,coverage:parts.length,totalProxy:5};
 }
 function evaluate(record,sources={},now=new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Shanghai'})){
  const a=record.recommendationAudit||{},reasons=[],hasSource=id=>!!sources[id]?.url;
  if(a.locationConfirmed!==true||!a.locationSourceIds?.length||!a.locationSourceIds.every(hasSource))reasons.push('具体营位或可搭帐篷区域尚未核实');
  const m=a.management;
  if(!m||m.scope!=='specific-camp'||m.dayCampingAllowed!==true||!fresh(m.date,now,90)||!hasSource(m.sourceId)||m.role!=='operator')reasons.push('缺少近90天管理方开放与日营许可依据');
  const posts=(a.posts||[]).filter(p=>p.bodyRead===true&&p.locationMatched===true&&p.sponsored===false&&fresh(p.date,now,365)&&hasSource(p.sourceId)&&sources[p.sourceId].author);
  const authors=new Set(posts.map(p=>sources[p.sourceId].author));
  if(authors.size<3)reasons.push('不足3位独立作者的近12个月有效实地反馈');
  if(record.conflict||a.unresolvedConflict===true)reasons.push('存在尚未解决的信息分歧');
  let available=0;const evidence=a.criteria||{};
  const values=dimensions.map(d=>d.items.map(([key])=>{const c=evidence[key];if(!c||![0,1].includes(c.value)||!c.sourceIds?.length||!c.sourceIds.every(hasSource)||!fresh(c.observedOn,now,90)||!c.measurement)return null;if(['clean','quiet'].includes(key)&&new Set((c.observationDates||[]).filter(x=>fresh(x,now,90))).size<2)return null;available++;return c.value;}));
  if(available!==20)reasons.push(`20项评分条件中，${20-available}项缺少可追溯的近期观察`);
  if(a.scenario!=='self-equipped-day')reasons.push('尚未完成自带装备日营场景评估');
  if(reasons.length){const proxy=provisional(record);return proxy?{...proxy,reasons,available,total:20,dimensions}:{status:'unrated',score:null,stars:null,reasons,available,total:20,dimensions};}
  const subscores=values.map(v=>v.reduce((s,n)=>s+n,0)),score=subscores.reduce((s,n)=>s+n,0)/4;
  // Exhaustive sensitivity check: 15–35% in five-point steps, weights sum to 100%.
  const variants=[];for(let a=15;a<=35;a+=5)for(let b=15;b<=35;b+=5)for(let c=15;c<=35;c+=5){let d=100-a-b-c;if(d>=15&&d<=35)variants.push(subscores.reduce((s,n,i)=>s+n*[a,b,c,d][i]/100,0));}
  return {status:'rated',score,stars:Math.round(score*2)/2,range:[Math.min(...variants),Math.max(...variants)],subscores,dimensions,available,total:20,reasons:[]};
 }
 const api={evaluate,dimensions,proxyDimensions};root.CampRatings=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
