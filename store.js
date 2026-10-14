'use strict';
window.CampStore = (() => {
  const pending = new Map();
  async function json(url, milliseconds = 12000) {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), milliseconds);
    try { const r = await fetch(url, { signal: controller.signal }); if (!r.ok) throw Error('资料请求失败（' + r.status + '）'); return await r.json(); }
    catch (e) { throw Error(e.name === 'AbortError' ? '资料请求超时，请重新加载' : e.message); }
    finally { clearTimeout(timer); }
  }
  function validateIndex(data) {
    if (data?.schemaVersion !== 2 || !Array.isArray(data.records) || !data.sources || !data.policy || !data.maintenance) throw Error('资料格式不完整，请重新加载');
    const ids = new Set();
    for (const r of data.records) {
      if (!/^C\d+$/.test(r.id) || ids.has(r.id) || typeof r.name !== 'string' || !Array.isArray(r.tags) || !Array.isArray(r.sourceIds) || !/^details\/C\d+\.json\?v=[a-f0-9]{12}$/.test(r.detailUrl)) throw Error('地点索引无效');
      if (r.sourceIds.some(id => !CampDomain.https(data.sources[id]?.url))) throw Error('地点来源缺失');
      ids.add(r.id);
    }
    data.sources=Object.assign(Object.create(null),data.sources);
    data.verifiedRows = []; CampDomain.configure(data.policy); return data;
  }
  async function detail(data, id) {
    const r = data.records.find(r => r.id === id);
    if (!r) throw Error('地点不存在');
    if (r.detailsLoaded) return r;
    const key = r.detailUrl;
    if (!pending.has(key)) pending.set(key, json(key).then(d => {
      if (d?.schemaVersion !== 2 || d.record?.id !== id || !Array.isArray(d.record.evidence) || !Array.isArray(d.record.sourceIds) || !d.sources || !Array.isArray(d.verifiedRows)) throw Error('地点详情格式无效');
      if(d.record.sourceIds.some(sid=>!CampDomain.https(d.sources[sid]?.url))||d.record.evidence.some(e=>!d.record.sourceIds.includes(e.sourceId))||d.verifiedRows.some(row=>row.recordId!==id||!Array.isArray(row.notes)||row.notes.some(n=>!CampDomain.https(n.url))))throw Error('地点详情的来源关联无效');
      const extensions = { location: r.location, routeSnapshot: r.routeSnapshot, images: r.images };
      Object.assign(r, d.record, extensions, { detailsLoaded: true }); Object.assign(data.sources, d.sources);
      const rows = new Map(data.verifiedRows.map(v => [v.rowNumber, v])); d.verifiedRows.forEach(v => rows.set(v.rowNumber, v)); data.verifiedRows = [...rows.values()];
      return r;
    }).finally(() => pending.delete(key)));
    return pending.get(key);
  }
  async function workbook(data) {
    if (data.workbookLoaded) return;
    if (!/^workbook\.json\?v=[a-f0-9]{12}$/.test(data.workbookUrl)) throw Error('来源资料地址无效');
    const key = data.workbookUrl;
    if (!pending.has(key)) pending.set(key, json(key).then(d => {
      if (d?.schemaVersion !== 2 || !Array.isArray(d.verifiedRows)||d.verifiedRows.some(row=>!Array.isArray(row.notes)||row.notes.length!==3||row.notes.some(n=>!CampDomain.https(n.url)))) throw Error('来源资料不完整');
      data.verifiedRows = d.verifiedRows; data.workbookLoaded = true;
    }).finally(() => pending.delete(key)));
    return pending.get(key);
  }
  return { json, validateIndex, detail, workbook };
})();
