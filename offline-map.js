'use strict';
// A local geographic snapshot, following the Qingdao itinerary's no-tile rendering.
window.CampMap=(()=>{
 let loading;
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function data(){if(!loading)loading=fetch('basemap.geojson?v=5').then(r=>{if(!r.ok)throw Error('地图资料加载失败');return r.json();}).then(d=>{if(d.type!=='FeatureCollection'||!d.features?.length)throw Error('地图资料不完整');return d;}).catch(e=>{loading=null;throw e;});return loading;}
 function roadPosition(f){let c=f.geometry.coordinates;if(f.geometry.type==='MultiLineString')c=[...c].sort((a,b)=>b.length-a.length)[0];return c[Math.floor(c.length/2)];}
 async function attach(map,{compact=false}={}){
  const host=map.getContainer();host.classList.add('local-basemap');host.setAttribute('aria-label','杭州区域参考地图');const state=document.createElement('div');state.className='basemap-state';state.textContent='正在加载本地地图…';host.append(state);
  try{
   const d=await data();if(!host.isConnected)return;
   const bounds=L.latLngBounds([d.bbox[1],d.bbox[0]],[d.bbox[3],d.bbox[2]]);map.setMaxBounds(bounds.pad(.18));map.setMinZoom(compact?11:10);map.setMaxZoom(16);
   map.createPane('base-geography');map.getPane('base-geography').style.zIndex=220;
   map.createPane('base-labels');map.getPane('base-labels').style.zIndex=350;map.getPane('base-labels').style.pointerEvents='none';
   const renderer=L.canvas({pane:'base-geography',padding:.3});
   const shapes=d.features.filter(f=>!['district','water-label'].includes(f.properties.kind));
   const roads=shapes.filter(f=>f.properties.kind==='road'),labels=d.features.filter(f=>['district','water-label'].includes(f.properties.kind));
   const base=L.geoJSON(shapes,{renderer,interactive:false,style:f=>{
    const p=f.properties;if(p.kind==='water')return {color:'#b4cfd0',weight:.65,fillColor:'#d8e9e8',fillOpacity:1};
    if(p.kind==='park')return {color:'#d3dfcc',weight:.5,fillColor:'#e1ebd8',fillOpacity:1};
    if(p.kind==='river')return {color:'#b5d3d7',weight:1.3,opacity:.85};
    const major=['motorway','trunk','primary'].includes(p.class);return {color:major?'#cdbf9d':p.class==='secondary'?'#d2ccbb':'#d6dcd4',weight:major?2.1:1.1,opacity:.95};
   }}).addTo(map);
   host.dataset.baseFeatures=String(shapes.length);host.dataset.basemap='local';
   const text=L.layerGroup().addTo(map);
   function refresh(){text.clearLayers();const z=map.getZoom(),used=[],seen=new Set(),view=map.getBounds(),size=map.getSize();
    const add=(ll,name,cls)=>{if(!name||seen.has(name)||!view.contains(ll))return;const pt=map.latLngToContainerPoint(ll);if(pt.x<30||pt.x>size.x-30||pt.y<(compact?10:80)||pt.y>size.y-(compact?10:230)||used.some(p=>Math.abs(p.x-pt.x)<78&&Math.abs(p.y-pt.y)<25))return;seen.add(name);used.push(pt);L.marker(ll,{interactive:false,keyboard:false,pane:'base-labels',icon:L.divIcon({className:cls,html:esc(name),iconSize:[100,18],iconAnchor:[50,9]})}).addTo(text);};
    labels.forEach(f=>{if(f.properties.kind==='district'&&z>13)return;const c=f.geometry.coordinates;add([c[1],c[0]],f.properties.name,f.properties.kind==='water-label'?'base-water-label':'base-district-label');});
    if(z>=12){for(const f of roads){if(used.length>=(compact?7:16))break;if(!f.properties.name||f.properties.class==='motorway')continue;const c=roadPosition(f);add([c[1],c[0]],f.properties.name,'base-road-label');}}
   }
   map.on('moveend zoomend resize',refresh);refresh();
   map.attributionControl.addAttribution('© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · <a href="basemap.geojson" target="_blank">区域数据 '+d.snapshotAt.slice(0,10)+'</a>');
   state.textContent='本地地图 · 主干道路参考';state.title=d.scope;state.classList.add('ready');
   L.control.scale({imperial:false,position:'bottomleft',maxWidth:75}).addTo(map);
   return {base,refresh};
  }catch(e){state.className='basemap-notice';state.innerHTML='<strong>地图资料未能加载</strong><span>请刷新重试，或使用营地导航入口</span>';host.dataset.basemap='failed';}
 }
 return {attach};
})();
