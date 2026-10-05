// Kiosco de la casa: reloj con la hora del servidor, clima, listas y modo oscuro en descanso.
(function () {
  "use strict";

  var POLL_MS = 60000;
  var DAYS = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];
  var MONTHS = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
  ];
  var offset = 0;

  function byId(id) {
    return document.getElementById(id);
  }

  function pad(number) {
    return number < 10 ? "0" + number : String(number);
  }

  function clear(element) {
    while (element.firstChild) {
      element.removeChild(element.firstChild);
    }
  }

  function tick() {
    var now = new Date(Date.now() + offset);
    byId("time").textContent = pad(now.getHours()) + ":" + pad(now.getMinutes());
    byId("date").textContent =
      DAYS[now.getDay()] + " " + now.getDate() + " de " + MONTHS[now.getMonth()];
  }

  function fillList(id, items) {
    var list = byId(id);
    clear(list);
    if (!items || items.length === 0) {
      var empty = document.createElement("li");
      empty.className = "empty";
      empty.textContent = "Nada por ahora";
      list.appendChild(empty);
      return;
    }
    items.forEach(function (text) {
      var item = document.createElement("li");
      item.textContent = text;
      list.appendChild(item);
    });
  }

  function fillToday(entries) {
    var list = byId("today");
    clear(list);
    if (!entries || entries.length === 0) {
      var empty = document.createElement("li");
      empty.className = "empty";
      empty.textContent = "Nada para hoy";
      list.appendChild(empty);
      return;
    }
    entries.forEach(function (entry) {
      var item = document.createElement("li");
      if (entry.past) {
        item.className = "past";
      }
      var dot = document.createElement("span");
      dot.className = "dot";
      dot.style.backgroundColor = entry.color;
      var hour = document.createElement("span");
      hour.className = "hour";
      hour.textContent = entry.time || "Todo el día";
      var title = document.createElement("span");
      title.textContent = entry.title;
      item.appendChild(dot);
      item.appendChild(hour);
      item.appendChild(title);
      list.appendChild(item);
    });
  }

  function showWeather(weather) {
    var box = byId("weather");
    if (!weather) {
      box.hidden = true;
      return;
    }
    var sky = weather.sky || "";
    byId("temperature").textContent = weather.temperature + "°";
    byId("sky").textContent = sky.charAt(0).toUpperCase() + sky.slice(1);
    byId("range").textContent =
      "Máx " + weather.maximum + "° · Mín " + weather.minimum + "° · Lluvia " +
      weather.rain_chance + "%";
    box.hidden = false;
  }

  function render(data, sentAt, receivedAt) {
    var server = Date.parse(data.now);
    if (!isNaN(server)) {
      offset = server - (sentAt + receivedAt) / 2;
    }
    document.body.classList.toggle("dark", Boolean(data.quiet));
    showWeather(data.weather);
    fillToday(data.today);
    var lists = data.lists || {};
    fillList("list-compras", lists.compras);
    fillList("list-pendientes", lists.pendientes);
    byId("problems").textContent = (data.problems || []).join(" ");
    tick();
  }

  function poll() {
    var sentAt = Date.now();
    fetch("/api/board", { cache: "no-store" })
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

  function goFullscreen() {
    var root = document.documentElement;
    if (document.fullscreenElement || !root.requestFullscreen) {
      return;
    }
    var asked = root.requestFullscreen();
    if (asked && asked.catch) {
      asked.catch(function () {});
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.addEventListener("click", goFullscreen);
    tick();
    poll();
    setInterval(tick, 1000);
    setInterval(poll, POLL_MS);
  });
})();
