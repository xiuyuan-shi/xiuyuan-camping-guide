'use strict';
(function (root) {
  const weatherCodes=new Set([0,1,2,3,45,48,51,53,55,56,57,61,63,65,66,67,71,73,75,77,80,81,82,85,86,95,96,99]);
  const defaults = { roadSnapMaxMeters: 500, weatherCacheMinutes: 20, weatherModelMaxAgeHours: 3, referenceScoreMaxAgeDays: 90 };
  let policy = { ...defaults };
  const today = (now = new Date()) => {
    const p = Object.fromEntries(new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now).map(x => [x.type, x.value]));
    return `${p.year}-${p.month}-${p.day}`;
  };
  function https(value) {
    try { const u = new URL(value); return u.protocol === 'https:' && !u.username && !u.password; } catch { return false; }
  }
  const samePoint = (a, b) => Number.isFinite(a?.latitude) && Number.isFinite(a?.longitude) && a.latitude === b?.latitude && a.longitude === b?.longitude;
  const pointValid = p => Number.isFinite(p?.latitude) && Number.isFinite(p?.longitude) && Math.abs(p.latitude) <= 90 && Math.abs(p.longitude) <= 180;
  function meters(a, b) {
    const rad = x => x * Math.PI / 180, lat = rad(b.latitude - a.latitude), lon = rad(b.longitude - a.longitude);
    const h = Math.sin(lat / 2) ** 2 + Math.cos(rad(a.latitude)) * Math.cos(rad(b.latitude)) * Math.sin(lon / 2) ** 2;
    return 6371000 * 2 * Math.asin(Math.min(1, Math.sqrt(h)));
  }
  function routeIssue(v, destination, origin) {
    if (!v || !samePoint(v.originLocation, origin) || !samePoint(v.destinationLocation, destination)) return '路线起点或终点已经变化';
    if (!Number.isFinite(v.duration) || v.duration <= 0 || !Number.isFinite(v.distance) || v.distance <= 0) return '路线里程或时长无效';
    if (!Array.isArray(v.waypoints) || v.waypoints.length !== 2 || v.waypoints.some(p => !Number.isFinite(p.distance) || p.distance < 0 || p.distance > policy.roadSnapMaxMeters)) return `参考点距匹配道路超过${policy.roadSnapMaxMeters}米或匹配资料不完整`;
    return null;
  }
  function geometryIssue(d, snapshot, destination, origin) {
    const cs = d?.geometry?.coordinates;
    if (d?.geometry?.type !== 'LineString' || !Array.isArray(cs) || cs.length < 2 || cs.some(c => !Array.isArray(c) || c.length !== 2 || !pointValid({ longitude: c[0], latitude: c[1] }))) return '路线几何不完整';
    if (!samePoint(d.originLocation, origin) || d.distance !== snapshot.distance || d.duration !== snapshot.duration) return '路线文件与快照不一致';
    if (meters({ longitude: cs[0][0], latitude: cs[0][1] }, origin) > policy.roadSnapMaxMeters || meters({ longitude: cs.at(-1)[0], latitude: cs.at(-1)[1] }, destination) > policy.roadSnapMaxMeters) return '路线几何端点与参考点不一致';
    return null;
  }
  function weatherIssue(w, now = new Date()) {
    const current = w?.current, daily = w?.daily, dates = daily?.time;
    if (!current || !Number.isFinite(current.temperature_2m) || !weatherCodes.has(current.weather_code) || !Array.isArray(dates) || dates.length !== 7) return '天气响应不完整';
    const date = today(now), time = Date.parse(current.time + '+08:00'), age = now.getTime() - time;
    if (!Number.isFinite(time) || age < -30 * 60000 || age > policy.weatherModelMaxAgeHours * 3600000 || dates[0] !== date) return '天气模型或预报日期已过期，请重新查询';
    if(![0,1].includes(current.is_day)||!Number.isFinite(current.apparent_temperature)||!Number.isFinite(current.relative_humidity_2m)||current.relative_humidity_2m<0||current.relative_humidity_2m>100||!Number.isFinite(current.wind_speed_10m)||current.wind_speed_10m<0)return '当前天气字段无效';
    for (let n = 0; n < 7; n++) {
      const expected = new Date(Date.parse(date + 'T00:00:00Z') + n * 86400000).toISOString().slice(0, 10);
      if (dates[n] !== expected) return '天气预报日期不连续';
    }
    for (const k of ['weather_code', 'temperature_2m_max', 'temperature_2m_min', 'precipitation_probability_max', 'precipitation_sum', 'wind_speed_10m_max', 'wind_gusts_10m_max', 'sunrise', 'sunset']) {
      if (!Array.isArray(daily[k]) || daily[k].length !== 7) return '天气逐日字段不完整';
    }
    if(daily.precipitation_probability_max.some(x=>x!==null&&(!Number.isFinite(x)||x<0||x>100))||daily.precipitation_sum.some(x=>x!==null&&(!Number.isFinite(x)||x<0)))return '降水字段无效';
    if(['wind_speed_10m_max','wind_gusts_10m_max'].some(k=>daily[k].some(x=>x!==null&&(!Number.isFinite(x)||x<0))))return '风速字段无效';
    if(['sunrise','sunset'].some(k=>daily[k].some((x,i)=>x!==null&&(!/^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d$/.test(x)||x.slice(0,10)!==dates[i]))))return '日出日落字段无效';
    if (daily.weather_code.some(x => !weatherCodes.has(x)) || daily.temperature_2m_min.some(x => !Number.isFinite(x)) || daily.temperature_2m_max.some(x => !Number.isFinite(x))) return '天气数值无效';
    return null;
  }
  function photoAllowed(p) {
    return p?.permission === 'allowed' && p.associationConfirmed === true && !!p.author && !!p.license && https(p.licenseUrl) && https(p.sourceUrl) && (https(p.url) || /^assets\/photos\/[a-z0-9-]+\.jpg$/.test(p.url)) && !/[?&](sign|expires|x-expires|xsec_token)=/i.test(p.url);
  }
  const values = (r, key) => r.claimedValues?.[key] || (r.evidence || []).flatMap(e => (e.fields || []).filter(f => f.key === key).map(f => f.value));
  function facilityState(r, key) {
    if (r.primaryFacts?.[key]) return r.primaryFacts[key].status;
    const text = values(r, key).join('；');
    if (!text || /待核|未知|未确认|未细化|未给|未提供|非许可|不确定/.test(text)) return 'unknown';
    const no = key === 'toilet' ? /无厕所|没有厕所|无卫生间/ : key === 'stove' ? /禁止|禁明火|不能|不可|不允许/ : /不能|不可|禁止|不允许|不支持/;
    const yes = key === 'toilet' ? /有.*厕所|公厕|卫生间|公共厕所/ : key === 'stove' ? /(?:可|允许|支持).{0,8}卡式炉|卡式炉.{0,8}(?:可|允许)/ : /(?:可|允许|支持).{0,8}过夜|过夜.{0,8}(?:可|允许)/;
    if (no.test(text)) return yes.test(text) ? 'conflict' : 'no';
    return yes.test(text) ? 'yes' : 'unknown';
  }
  function feeState(r) {
    if (r.primaryFacts?.fee) return r.primaryFacts.fee.status;
    const text = values(r, 'fee').join('；');
    if (!text || /未知|待核|冲突|不一致/.test(text)) return 'unknown';
    const free = /免费|不收费|无收费/.test(text), paid = /付费|收费|\d+\s*元/.test(text.replace(/不收费|无收费|未收费/g, ''));
    return free && paid ? 'conflict' : free ? 'free' : paid ? 'paid' : 'unknown';
  }
  function audienceText(r) {
    const claims=values(r,'audience');
    if(claims.some(t=>/不适合|暂不能确认|不建议|不推荐|不宜/.test(t)))return '';
    return [...(r.tags || []).filter(t => /^适合/.test(t)), ...claims].join(' ');
  }
  function displayTags(r){return (r.tags||[]).filter(tag=>!/^适合/.test(tag)||!!audienceText(r));}
  function matches(r, f) {
    if (r.scope !== (f.scope || 'hangzhou')) return false;
    const words = r.searchText || [r.name, r.type, r.area, ...(r.tags || []), ...(r.aliases || [])].join(' ').toLowerCase();
    if (f.query && !words.includes(f.query.trim().toLowerCase())) return false;
    const environment = { '湖|水库|江景|水边|溪': /湖|水库|江景|水边|溪|河/, '林|树荫|树': /林|树荫|树/, '公园': /公园|草坪|草地/, '徒步|骑行': /徒步|骑行/, '经营营地': /经营营地/ };
    if (f.environment && !(environment[f.environment]?.test([r.type, ...(r.tags || []), ...values(r, 'environment')].join(' ')))) return false;
    const audience = { '亲子|儿童|小朋友': /亲子|儿童|小朋友/, '老人|长辈': /老人|长辈/, '情侣|双人': /情侣|双人/ };
    if (f.audience && !audience[f.audience]?.test(audienceText(r))) return false;
    if (f.facility && facilityState(r, f.facility) !== 'yes') return false;
    const fee = feeState(r);
    if (f.budget && !(f.budget === 'free' ? fee === 'free' : f.budget === 'priced' ? fee === 'paid' : f.budget === 'unknown' ? ['unknown', 'conflict'].includes(fee) : false)) return false;
    if (f.bounds && (!pointValid(r.location) || r.location.longitude < f.bounds[0] || r.location.latitude < f.bounds[1] || r.location.longitude > f.bounds[2] || r.location.latitude > f.bounds[3])) return false;
    return true;
  }
  // Merge nearby projected markers; every reference remains selectable in its group.
  function clusterPoints(points, radius = 36) {
    const groups = points.map(p => ({x:p.x,y:p.y,items:[p]}));
    for (let i = 0; i < groups.length; i++) {
      for (let j = i + 1; j < groups.length; j++) {
        if (Math.hypot(groups[i].x-groups[j].x,groups[i].y-groups[j].y) >= radius) continue;
        groups[i].items.push(...groups[j].items);
        groups[i].x = groups[i].items.reduce((n,p)=>n+p.x,0)/groups[i].items.length;
        groups[i].y = groups[i].items.reduce((n,p)=>n+p.y,0)/groups[i].items.length;
        groups.splice(j,1);
        // Moving the group centre can bring it near an earlier group.
        i = -1;
        break;
      }
    }
    return groups;
  }
  root.CampDomain = { configure: p => { const next={...defaults,...p};for(const [key,max] of Object.entries(defaults))if(!Number.isFinite(next[key])||next[key]<=0||next[key]>max)throw Error('数据校验规则无效：'+key);policy=next; }, get policy() { return policy; }, today, https, pointValid, samePoint, meters, routeIssue, geometryIssue, weatherIssue, photoAllowed, values, facilityState, feeState, audienceText, displayTags, matches, clusterPoints };
})(typeof window === 'undefined' ? globalThis : window);
