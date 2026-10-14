'use strict';
window.CampServices = (() => {
  const pending = new Map(), weather = new Map(), routes = new Map();
  let config;
  const stamp = () => new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false });
  function read(key, ttl) { try { const v = JSON.parse(localStorage.getItem(key)); return v && Date.now() >= v.at && Date.now() - v.at < ttl ? v.data : null; } catch { return null; } }
  function write(key, data) { try { localStorage.setItem(key, JSON.stringify({ at: Date.now(), data })); } catch {} }
  async function once(key, make) { if (!pending.has(key)) pending.set(key, make().finally(() => pending.delete(key))); return pending.get(key); }
  async function getWeather(r, force = false) {
    if (!CampDomain.pointValid(r.location)) throw Error('参考坐标尚未核实');
    if (!config?.providers?.weather) throw Error('天气服务尚未加载，请稍后重试');
    const g = r.location, key = `camp-weather-v2:${g.latitude.toFixed(5)},${g.longitude.toFixed(5)}`;
    const cached = !force && read(key, CampDomain.policy.weatherCacheMinutes * 60000);
    if (cached && !CampDomain.weatherIssue(cached)) { weather.set(r.id, cached); return cached; }
    const result = await once(key, async () => {
      const u = new URL(config.providers.weather);
      Object.entries({ latitude: g.latitude, longitude: g.longitude, current: 'temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,is_day', daily: 'weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,precipitation_sum,wind_speed_10m_max,wind_gusts_10m_max,sunrise,sunset', timezone: 'Asia/Shanghai', wind_speed_unit: 'ms', forecast_days: 7 }).forEach(([k,v]) => u.searchParams.set(k,v));
      const d = await CampStore.json(u.href, 18000), issue = CampDomain.weatherIssue(d); if (issue) throw Error(issue);
      const v = { ...d, queriedAt: stamp(), requestedLocation: { ...g } }; write(key, v); return v;
    });
    weather.set(r.id, result); return result;
  }
  async function getRoute(r, geometry = false) {
    if (!CampDomain.pointValid(r.location)) throw Error('参考位置尚未核实');
    if (!config?.origin) throw Error('路线服务尚未加载');
    const g = r.location, origin = config.origin, saved = r.routeSnapshot;
    if (saved && CampDomain.routeIssue(saved, g, origin)) throw Error('已保存路线待复核：' + CampDomain.routeIssue(saved, g, origin));
    if (saved) {
      if (geometry && !saved.geometry) {
        if (!/^routes\/C\d+\.json(?:\?v=[\w.-]+)?$/.test(saved.geometryUrl || '')) throw Error('路线文件地址无效');
        const d = await once('geometry:' + saved.geometryUrl, () => CampStore.json(saved.geometryUrl));
        const issue = CampDomain.geometryIssue(d, saved, g, origin); if (issue) throw Error(issue); saved.geometry = d.geometry;
      }
      if(geometry){const issue=CampDomain.geometryIssue(saved,saved,g,origin);if(issue)throw Error(issue);}
      routes.set(r.id, saved); return saved;
    }
    if (!config.providers?.routing) throw Error('路线服务不可用');
    const key = `camp-route-v3:${origin.longitude},${origin.latitude}:${g.longitude},${g.latitude}`, cached = read(key, 86400000);
    if (cached && !CampDomain.routeIssue(cached, g, origin) && (!geometry||!CampDomain.geometryIssue(cached,cached,g,origin))) { routes.set(r.id,cached); return cached; }
    const v = await once(key, async () => {
      const u = config.providers.routing + `${origin.longitude},${origin.latitude};${g.longitude},${g.latitude}?overview=full&geometries=geojson&steps=false`, d = await CampStore.json(u,18000);
      if (d.code !== 'Ok' || !d.routes?.length) throw Error('未找到参考驾车路线');
      const route = { ...d.routes[0], waypoints: d.waypoints, originLocation: origin, destinationLocation: g, origin: origin.name, sourceUrl: 'https://project-osrm.org/', queriedAt: stamp() }, issue = CampDomain.routeIssue(route,g,origin);
      if (issue) throw Error(issue);
      const geometryIssue = CampDomain.geometryIssue(route,route,g,origin); if (geometryIssue) throw Error(geometryIssue);
      write(key,route); return route;
    });
    routes.set(r.id,v); return v;
  }
  function routeText(r) {
    const v = routes.get(r.id) || r.routeSnapshot;
    if (v && config && !CampDomain.routeIssue(v,r.location,config.origin)) return `约${Math.round(v.distance / 1000)}km · ${Math.max(.5,Math.round(v.duration / 1800) / 2).toFixed(1)}小时`;
    return r.location ? r.routeSnapshot ? '参考车程待复核' : '参考车程待查询' : config ? '具体地点待定位' : '位置资料加载中';
  }
  return { configure: c => { config = c; }, getWeather, getRoute, routeText, weather, routes };
})();
