const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const root=path.join(__dirname,'..'),ctx={URL,Intl,Date};vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(root,'domain.js'),'utf8'),ctx);const domain=ctx.CampDomain;
const data=JSON.parse(fs.readFileSync(path.join(root,'data.json'))),live=JSON.parse(fs.readFileSync(path.join(root,'live-data.json'))),byId=Object.fromEntries(data.records.map(r=>[r.id,r]));
test('parent audience uses the same explicit tags; safety contradictions do not become a match',()=>{assert(domain.matches(byId.C207,{audience:'亲子|儿童|小朋友'}));assert(!domain.matches(byId.C024,{audience:'亲子|儿童|小朋友'}));assert(!domain.displayTags(byId.C024).includes('适合亲子'));});
test('conflicting costs stay in the unknown group; stove bans and non-specific BBQ claims do not imply permission',()=>{assert(domain.matches(byId.C028,{budget:'unknown'}));assert(!domain.matches(byId.C049,{facility:'stove'}));assert(!domain.matches({scope:'hangzhou',claimedValues:{stove:['作者介绍烧烤活动']},tags:[]},{facility:'stove'}));});
test('road boundary and both endpoints are checked for actual snapshots and changed destinations',()=>{const v=structuredClone(live.records.C104.routeSnapshot),g=live.records.C104.location,o=live.origin;assert.equal(domain.routeIssue(v,g,o),null);v.waypoints[1].distance=500;assert.equal(domain.routeIssue(v,g,o),null);v.waypoints[1].distance=501;assert(domain.routeIssue(v,g,o));v.waypoints[1].distance=0;assert(domain.routeIssue(v,{...g,latitude:g.latitude+1},o));assert(domain.routeIssue(live.records.C009.routeSnapshot,live.records.C009.location,o));});
test('route geometry must agree with its metadata and actual reference endpoints',()=>{for(const [id,r] of Object.entries(live.records)){if(domain.routeIssue(r.routeSnapshot,r.location,live.origin))continue;const geometry=JSON.parse(fs.readFileSync(path.join(root,r.routeSnapshot.geometryUrl.split('?')[0])));assert.equal(domain.geometryIssue(geometry,r.routeSnapshot,r.location,live.origin),null,id);const bad=structuredClone(geometry);bad.geometry.coordinates[0]=[0,0];assert(domain.geometryIssue(bad,r.routeSnapshot,r.location,live.origin));}});
const weather=require('./weather-fixture.cjs');
test('weather validates Shanghai model time, consecutive days, completeness and numerical values',()=>{const now=new Date('2026-10-14T12:10:00+08:00');assert.equal(domain.weatherIssue(weather(),now),null);for(const mutate of [w=>w.current.time='2026-09-13T12:00',w=>w.daily.time[0]='2026-09-13',w=>w.daily.temperature_2m_max.pop(),w=>w.current.weather_code=12345,w=>w.daily.precipitation_probability_max[0]=101,w=>w.daily.wind_gusts_10m_max[0]='<svg>',w=>w.daily.sunset[0]='<script>']){const w=weather();mutate(w);assert(domain.weatherIssue(w,now));}});
test('displayed photos retain their actual evidence status and use safe stable image URLs',()=>{
 const photos=data.records.flatMap(r=>r.displayPhotos);for(const p of photos)assert(domain.photoAllowed(p));
 const p=structuredClone(photos.find(p=>p.permission==='allowed'&&p.displayBasis!=='restored-previous'));
 assert(!domain.photoAllowed({...p,permission:'unknown'}));assert(!domain.photoAllowed({...p,associationConfirmed:false}));assert(!domain.photoAllowed({...p,url:'https://example.org/image.jpg?sign=fixture'}));
 for(const status of ['exclude','withheld','unavailable'])assert(!domain.photoAllowed({...p,status}));assert(!domain.photoAllowed({...p,permission:'denied'}));assert(!domain.photoAllowed({...p,review:{status:'exclude'}}));
 const restored=photos.find(p=>p.displayBasis==='restored-previous');assert(restored);assert(!restored.permission);assert(!domain.photoAllowed({...restored,url:'javascript:alert(1)'}));assert(!domain.photoAllowed({...restored,permission:'denied'}));assert(!domain.photoAllowed({...restored,status:'exclude'}));assert(!domain.photoAllowed({...restored,restoredFrom:''}));
});
test('spatial filters exclude outside points and malformed policy cannot widen the route limit',()=>{const r={scope:'hangzhou',tags:[],location:{latitude:30,longitude:120}};assert(domain.matches(r,{bounds:[119,29,121,31]}));assert(!domain.matches(r,{bounds:[121,29,122,31]}));assert.throws(()=>domain.configure({roadSnapMaxMeters:1500}));});
test('dense map groups retain every point, separate as the view expands, and handle coincident references',()=>{
 const points=[{id:'a',x:0,y:0},{id:'b',x:20,y:0},{id:'c',x:21,y:0},{id:'d',x:100,y:100}];
 const groups=domain.clusterPoints(points);assert.equal(groups.length,2);assert.deepEqual(Array.from(groups.flatMap(g=>g.items.map(p=>p.id))).sort(),['a','b','c','d']);
 for(let i=0;i<groups.length;i++)for(let j=i+1;j<groups.length;j++)assert(Math.hypot(groups[i].x-groups[j].x,groups[i].y-groups[j].y)>=36);
 assert.equal(domain.clusterPoints(points.map(p=>({...p,x:p.x*50,y:p.y*50}))).length,4);
 assert.equal(domain.clusterPoints([{id:'a',x:1,y:1},{id:'b',x:1,y:1}])[0].items.length,2);
});

