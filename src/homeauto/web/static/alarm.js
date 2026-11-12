// Vista de alarma en la tele: hora en que sonó, mensaje y fecha; al dejar de sonar o al tope vuelve al kiosco.
(function () {
  "use strict";

  var POLL_MS = 5000;
  var MAX_VIEW_MS = 2100000;
  var KIOSK = "/pantalla?ver=1";
  var DAYS = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];
  var MONTHS = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
  ];

  // El número de la alarma de la dirección, o null.
  function jobFrom(search) {
    var match = /[?&]job=(\d+)(?:&|$)/.exec(search || "");
    return match ? parseInt(match[1], 10) : null;
  }

  // Adónde ir: null mientras suena y no pasó MAX_VIEW_MS desde que se cargó, si no el kiosco.
  function nextPage(data, shownMs) {
    return data && data.ringing && shownMs < MAX_VIEW_MS ? null : KIOSK;
  }

  // Adónde ir con el feed caído: null hasta MAX_VIEW_MS desde que se cargó, después el kiosco.
  function offlinePage(shownMs) {
    return shownMs < MAX_VIEW_MS ? null : KIOSK;
  }

  // Para quién es la alarma, o vacío si no es de nadie en particular.
  function forText(data) {
    return data && data.for ? "Para " + data.for : "";
  }

  function pad(number) {
    return number < 10 ? "0" + number : String(number);
  }

  function clockText(date) {
    return pad(date.getHours()) + ":" + pad(date.getMinutes());
  }

  function dateText(date) {
    return DAYS[date.getDay()] + " " + date.getDate() + " de " + MONTHS[date.getMonth()];
  }

  // La hora grande: la de cuando sonó si el feed la trae, si no la actual.
  function alarmText(data, now) {
    return data && data.at ? data.at : clockText(now);
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { MAX_VIEW_MS: MAX_VIEW_MS, jobFrom: jobFrom, nextPage: nextPage,
      offlinePage: offlinePage, clockText: clockText, dateText: dateText, alarmText: alarmText,
      forText: forText };
  }
  if (typeof document === "undefined") {
    return;
  }

  var offset = 0;
  var last = null;
  var loadedAt = Date.now();
  var job = jobFrom(location.search);

  function byId(id) {
    return document.getElementById(id);
  }

  function tick() {
    var now = new Date(Date.now() + offset);
    byId("time").textContent = alarmText(last, now);
    byId("clock").textContent = clockText(now);
    byId("clock").hidden = !(last && last.at);
    byId("date").textContent = dateText(now);
  }

  function leave() {
    location.replace(KIOSK);
  }

  function render(data, sentAt, receivedAt) {
    var server = Date.parse(data.now);
    if (!isNaN(server)) {
      offset = server - (sentAt + receivedAt) / 2;
    }
    if (nextPage(data, Date.now() - loadedAt)) {
      leave();
      return;
    }
    last = data;
    byId("message").textContent = data.message || "";
    byId("for").textContent = forText(data);
    byId("for").hidden = !forText(data);
    byId("problems").textContent = "";
    tick();
  }

  function poll() {
    var sentAt = Date.now();
    fetch("/api/ringing/" + job, { cache: "no-store" })
      .then(function (response) {
        if (!response.ok) {
          throw new Error(String(response.status));
        }
        return response.json();
      })
      .then(function (data) {
        render(data, sentAt, Date.now());
      })
      .catch(function () {
        if (offlinePage(Date.now() - loadedAt)) {
          leave();
          return;
        }
        byId("problems").textContent = "Sin conexión con la casa.";
      });
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (job === null) {
      leave();
      return;
    }
    tick();
    poll();
    setInterval(tick, 1000);
    setInterval(poll, POLL_MS);
  });
})();
