// Runs before the app bundle. The HTML remains usable if this script fails too.
(function () {
  var root = document.getElementById('root');
  var status = document.getElementById('sg-arranque-estado');
  var retry = document.getElementById('sg-recargar');
  if (!root || !status || !retry) return;

  function show(message) {
    if (!root.hasChildNodes()) status.textContent = message;
  }

  retry.addEventListener('click', function (e) {
    e.preventDefault();
    if (retry.getAttribute('aria-disabled') === 'true') return;
    retry.setAttribute('aria-disabled', 'true');
    show('Recargando la aplicación…');

    // A stuck worker/cache must not prevent a manual retry. Keep user data
    // (including localStorage and IndexedDB) and other apps' caches intact.
    var limit = setTimeout(reload, 1500);
    function reload() {
      clearTimeout(limit);
      if (limit === null) return;
      limit = null;
      location.reload();
    }
    var jobs = [];
    if (navigator.serviceWorker && navigator.serviceWorker.getRegistration) {
      jobs.push(Promise.resolve().then(function () {
        return navigator.serviceWorker.getRegistration(location.href);
      }).then(function (reg) {
        if (!reg || reg.scope !== location.origin + '/') return;
        var worker = reg.active || reg.waiting || reg.installing;
        if (worker && worker.scriptURL === location.origin + '/sw.js') return reg.unregister();
      }));
    }
    if (window.caches && caches.keys) {
      jobs.push(Promise.resolve().then(function () { return caches.keys(); }).then(function (keys) {
        return Promise.all(keys.filter(function (key) {
          return key === 'sergio-api' || key === 'sergio-creator' ||
            key === 'workbox-precache-v2-' + location.origin + '/';
        }).map(function (key) { return caches.delete(key); }));
      }));
    }
    Promise.all(jobs).then(reload, reload);
  });

  window.addEventListener('error', function (e) {
    var tag = e.target && e.target.tagName;
    if (tag === 'SCRIPT' || tag === 'LINK' || e.target === window) {
      show('No se pudo cargar Sergio. Pulse Recargar para reintentar.');
    }
  }, true);
  window.addEventListener('unhandledrejection', function () {
    show('No se pudo iniciar Sergio. Pulse Recargar para reintentar.');
  });
  setTimeout(function () {
    show('Sergio está tardando en abrirse. Puede recargar o cerrar esta ventana.');
  }, 8000);
})();
