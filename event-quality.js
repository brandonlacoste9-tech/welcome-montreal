(function(root) {
  'use strict';
  const normalize = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]/g, '');
  const addOn = /ticketless|surclassement|\bvip\s+upgrade\b|salon des directeurs|repas restaurant|parking|stationnement/i;
  function cleanEvents(events) {
    const result = [];
    const groups = new Map();
    for (const input of events || []) {
      if (!input || !input.name || !/^\d{4}-\d{2}-\d{2}$/.test(input.date || '') || addOn.test(input.name)) continue;
      const e = {...input};
      const key = [normalize(e.name), normalize(e.venue), e.date].join('|');
      const candidates = groups.get(key) || [];
      // Distinct advertised performance times must survive; feeds without times
      // can enrich a matching dated listing instead of creating another card.
      const duplicate = candidates.find(x => !x.time || !e.time || x.time === e.time);
      if (duplicate) {
        for (const field of ['time','image','lat','lon','url','source','name_fr','note','note_fr']) {
          if (duplicate[field] == null || duplicate[field] === '') duplicate[field] = e[field];
        }
      } else {
        candidates.push(e); groups.set(key, candidates); result.push(e);
      }
    }
    return result.sort((a,b) => a.date.localeCompare(b.date) || (a.time || '').localeCompare(b.time || ''));
  }
  function freshness(updated, now = new Date()) {
    const stamp = /^\d{4}-\d{2}-\d{2}$/.test(updated || '') ? new Date(updated + 'T12:00:00-04:00') : new Date(updated);
    if (!updated || !Number.isFinite(stamp.getTime())) return 'unknown';
    return now - stamp > 48 * 60 * 60 * 1000 ? 'stale' : 'current';
  }
  const api = {cleanEvents, freshness};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.EventQuality = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
