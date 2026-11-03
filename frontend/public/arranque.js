// If Sergio's page does not paint (an old copy asking for a file that is gone
// after an update, a blocked script, a crash before React starts), the person
// sees a clear message and a button, never a black or white screen
// (owner, 2 Nov 2026: «la app a veces se buguea o se queda en negro»).
// A classic script so it runs even when the module bundle fails to load.
(function () {
  var shown = false;
  function painted() {
    var root = document.getElementById('root');
    return !!(root && root.children.length > 0);
  }
  function recover() {
    var jobs = [];
    try {
      if (navigator.serviceWorker && navigator.serviceWorker.getRegistrations) {
        jobs.push(navigator.serviceWorker.getRegistrations().then(function (rs) {
          return Promise.all(rs.map(function (r) { return r.unregister(); }));
        }));
      }
      if (window.caches && caches.keys) {
        jobs.push(caches.keys().then(function (ks) {
          return Promise.all(ks.map(function (k) { return caches.delete(k); }));
        }));
      }
    } catch (e) { /* nothing to drop */ }
    Promise.all(jobs).then(function () { location.reload(); }, function () { location.reload(); });
  }
  function show(why) {
    if (shown || painted()) return;
    shown = true;
    var dark = window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches;
    var box = document.createElement('div');
    box.setAttribute('role', 'alert');
    var s = box.style;
    s.position = 'fixed'; s.inset = '0'; s.display = 'grid'; s.placeItems = 'center'; s.padding = '24px';
    s.textAlign = 'center'; s.fontFamily = 'system-ui, sans-serif';
    s.background = dark ? '#0c0a09' : '#ffffff'; s.color = dark ? '#f5f5f7' : '#1d1d1f';
    box.innerHTML = '<div style="max-width:360px"><h1 style="font-size:20px;margin:0 0 8px">Sergio no pudo abrirse</h1>' +
      '<p style="margin:0 0 16px;opacity:.7;line-height:1.5">Suele pasar justo después de una actualización. Recargue para abrir la versión nueva.</p>' +
      '<button id="sg-recargar" style="border:0;border-radius:999px;padding:10px 22px;font-size:15px;font-weight:600;cursor:pointer;' +
      'background:' + (dark ? '#f5f5f7' : '#1d1d1f') + ';color:' + (dark ? '#0c0a09' : '#fff') + '">Recargar</button>' +
      '<p style="margin:16px 0 0;font-size:12px;opacity:.5">' + String(why || '').slice(0, 120) + '</p></div>';
    document.body.appendChild(box);
    var b = document.getElementById('sg-recargar');
    if (b) b.addEventListener('click', recover);
  }
  // 1. a script or style that fails to load
  window.addEventListener('error', function (e) {
    var t = e && e.target;
    if (t && (t.tagName === 'SCRIPT' || t.tagName === 'LINK')) setTimeout(function () { show('No se pudo cargar ' + (t.src || t.href || '').split('/').pop()); }, 300);
  }, true);
  // 2. an error before anything is on screen
  window.addEventListener('unhandledrejection', function (e) {
    setTimeout(function () { show(e && e.reason && e.reason.message); }, 1500);
  });
  // 3. nothing painted after a while (a slow disk gets 8 seconds)
  setTimeout(function () { show('Tardó demasiado en arrancar'); }, 8000);
})();
