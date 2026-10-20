// Vista de alarma en la tele: hora grande, mensaje y fecha; al minuto o al dejar de sonar vuelve al kiosco.
(function () {
  "use strict";

  var POLL_MS = 5000;
  var VIEW_MS = 60000;
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

  // Adónde ir: null mientras suena y no pasó VIEW_MS desde que se cargó, si no el kiosco.
  function nextPage(data, shownMs) {
    return data && data.ringing && shownMs < VIEW_MS ? null : KIOSK;
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

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { jobFrom: jobFrom, nextPage: nextPage, clockText: clockText, dateText: dateText };
  }
  if (typeof document === "undefined") {
    return;
  }

  var offset = 0;
  var loadedAt = Date.now();
  var job = jobFrom(location.search);

  function byId(id) {
    return document.getElementById(id);
  }

  function tick() {
    var now = new Date(Date.now() + offset);
    byId("time").textContent = clockText(now);
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
    byId("message").textContent = data.message || "";
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
