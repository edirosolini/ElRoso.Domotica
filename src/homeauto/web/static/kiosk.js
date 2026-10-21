// Kiosco de la casa: reloj con la hora del servidor, clima, lo próximo, idea del menú, listas para tachar y descanso.
(function () {
  "use strict";

  var POLL_MS = 60000;
  var MINUTE_MS = 60000;
  var KEEP_PAST = 2;
  var MEAL_CLASSES = { next: "on", past: "past" };
  var DAYS = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];
  var MONTHS = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
  ];

  // Cuánto falta para el comienzo, en horas y minutos redondeados para arriba.
  function untilText(start, now) {
    var minutes = Math.ceil((start - now) / MINUTE_MS);
    if (minutes <= 0) {
      return "ahora";
    }
    var hours = Math.floor(minutes / 60);
    var rest = minutes % 60;
    if (hours === 0) {
      return "en " + rest + " min";
    }
    return rest === 0 ? "en " + hours + " h" : "en " + hours + " h " + rest + " min";
  }

  // La línea de cuándo de «Lo próximo».
  function nextMeta(next, now) {
    if (next.tomorrow) {
      return "mañana · " + next.time;
    }
    return untilText(Date.parse(next.start), now) + " · " + next.time;
  }

  // Dónde va la marca «ahora»: después de lo pasado, o de lo de todo el día si no pasó nada.
  function nowIndex(entries) {
    var index = 0;
    var i;
    for (i = 0; i < entries.length; i += 1) {
      if (entries[i].past) {
        index = i + 1;
      }
    }
    if (index > 0) {
      return index;
    }
    while (index < entries.length && !entries[index].time) {
      index += 1;
    }
    return index;
  }

  // Lo de hoy con solo los últimos pasados, tantos como pide keep.
  function trimPast(entries, keep) {
    var past = 0;
    entries.forEach(function (entry) {
      if (entry.past) {
        past += 1;
      }
    });
    var skip = Math.max(0, past - keep);
    return entries.filter(function (entry) {
      if (entry.past && skip > 0) {
        skip -= 1;
        return false;
      }
      return true;
    });
  }

  // Cuánto queda de hoy: lo que todavía no pasó.
  function leftToday(entries) {
    return (entries || []).filter(function (entry) {
      return !entry.past;
    }).length;
  }

  // El texto de una entrada de hoy, con para quién es si es de alguien.
  function todayLabel(entry) {
    var text = entry.label || entry.title;
    return entry.for ? text + " · para " + entry.for : text;
  }

  // El cielo con mayúscula y la sensación térmica.
  function skyLine(weather) {
    var sky = weather.sky || "";
    return sky.charAt(0).toUpperCase() + sky.slice(1) + " · sensación " + weather.feels_like + "°";
  }

  // La leyenda de las vacaciones a partir de la vuelta «AAAA-MM-DDTHH:MM»; vacía si no hay.
  function awayText(away) {
    var match = /^\d{4}-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(away || "");
    if (!match) {
      return "";
    }
    var text = "De vacaciones hasta el " + match[2] + "/" + match[1];
    if (match[3] !== "00" || match[4] !== "00") {
      text += " a las " + match[3] + ":" + match[4];
    }
    return text;
  }

  // El título y las filas de la tarjeta del menú; null si no hay nada que mostrar.
  function mealView(meal) {
    if (!meal || !meal.items || meal.items.length === 0) {
      return null;
    }
    return {
      title: meal.tomorrow ? "🍽 Idea para mañana" : "🍽 Idea para hoy",
      rows: meal.items.map(function (item) {
        return {
          text: item.label + " · " + item.dish,
          className: MEAL_CLASSES[item.state] || "",
        };
      }),
    };
  }

  // Si la dirección pide solo lectura con «ver=1», como la tele.
  function readOnly(search) {
    return /[?&]ver=1(?:&|$)/.test(search || "");
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { untilText: untilText, nextMeta: nextMeta, nowIndex: nowIndex, skyLine: skyLine,
      trimPast: trimPast, awayText: awayText, readOnly: readOnly, mealView: mealView,
      todayLabel: todayLabel, leftToday: leftToday };
  }
  if (typeof document === "undefined") {
    return;
  }

  var offset = 0;
  var writable = false;
  var upcoming;

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

  function span(className, text) {
    var element = document.createElement("span");
    element.className = className;
    if (text) {
      element.textContent = text;
    }
    return element;
  }

  function emptyLine(text) {
    var item = document.createElement("li");
    item.className = "empty";
    item.textContent = text;
    return item;
  }

  function showNext() {
    var title = byId("next-title");
    var meta = byId("next-meta");
    if (upcoming === undefined) {
      return;
    }
    clear(meta);
    if (!upcoming) {
      title.textContent = "Nada más por hoy";
      title.classList.add("calm");
      return;
    }
    title.textContent = upcoming.title;
    title.classList.remove("calm");
    var source = span("pill", upcoming.source);
    source.style.setProperty("--c", upcoming.color);
    meta.appendChild(source);
    meta.appendChild(document.createTextNode(nextMeta(upcoming, Date.now() + offset)));
  }

  function tick() {
    var now = new Date(Date.now() + offset);
    byId("time").textContent = pad(now.getHours()) + ":" + pad(now.getMinutes());
    byId("date").textContent =
      DAYS[now.getDay()] + " " + now.getDate() + " de " + MONTHS[now.getMonth()];
    showNext();
  }

  // Saca un ítem de la lista y vuelve a pedir la pantalla.
  function crossOut(name, entry, item, button) {
    button.disabled = true;
    item.classList.add("done");
    fetch("/api/lists/" + encodeURIComponent(name) + "/" + entry.id + "/done", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
      cache: "no-store",
      credentials: "same-origin",
    })
      .then(function (response) {
        if (!response.ok && response.status !== 404) {
          throw new Error(String(response.status));
        }
        poll();
      })
      .catch(function () {
        button.disabled = false;
        item.classList.remove("done");
        byId("problems").textContent = "No pude tachar «" + entry.text + "».";
      });
  }

  // Suma a la lista lo escrito y vuelve a pedir la pantalla.
  function addItems(name, input, button) {
    var text = input.value.trim();
    if (!text) {
      return;
    }
    button.disabled = true;
    fetch("/api/lists/" + encodeURIComponent(name), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text }),
      cache: "no-store",
      credentials: "same-origin",
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error(String(response.status));
        }
        input.value = "";
        button.disabled = false;
        poll();
      })
      .catch(function () {
        button.disabled = false;
        byId("problems").textContent = "No pude agregar «" + text + "».";
      });
  }

  function wireAdder(name) {
    var form = byId("add-" + name);
    var input = byId("add-" + name + "-text");
    var button = form.querySelector("button");
    form.addEventListener("submit", function (submit) {
      submit.preventDefault();
      addItems(name, input, button);
    });
  }

  function showAdders() {
    byId("add-compras").hidden = !writable;
    byId("add-pendientes").hidden = !writable;
  }

  function fillList(name, items) {
    var list = byId("list-" + name);
    clear(list);
    byId("count-" + name).textContent = String(items ? items.length : 0);
    if (!items || items.length === 0) {
      list.appendChild(emptyLine("Nada por ahora"));
      return;
    }
    items.forEach(function (entry) {
      var item = document.createElement("li");
      if (writable) {
        var button = document.createElement("button");
        button.type = "button";
        button.className = "check";
        button.title = "Tachar «" + entry.text + "»";
        button.setAttribute("aria-label", "Tachar «" + entry.text + "»");
        button.addEventListener("click", function (click) {
          click.stopPropagation();
          crossOut(name, entry, item, button);
        });
        item.appendChild(button);
      }
      item.appendChild(span("", entry.text));
      list.appendChild(item);
    });
  }

  function nowLine() {
    var item = document.createElement("li");
    item.className = "now";
    item.appendChild(span("hour", "ahora"));
    item.appendChild(span("bar now-bar"));
    item.appendChild(span("what"));
    return item;
  }

  function fillToday(entries) {
    var list = byId("today");
    clear(list);
    byId("count-today").textContent = String(leftToday(entries));
    if (!entries || entries.length === 0) {
      list.appendChild(emptyLine("Nada para hoy"));
      return;
    }
    var shown = trimPast(entries, KEEP_PAST);
    var here = nowIndex(shown);
    shown.forEach(function (entry, index) {
      if (index === here) {
        list.appendChild(nowLine());
      }
      var item = document.createElement("li");
      if (entry.past) {
        item.className = "past";
      }
      var bar = span("bar");
      bar.style.setProperty("--c", entry.color);
      item.appendChild(span("hour", entry.time || "Todo el día"));
      item.appendChild(bar);
      item.appendChild(span("what", todayLabel(entry)));
      if (entry.past && entry.mark) {
        item.appendChild(span("mark", entry.mark));
      }
      list.appendChild(item);
    });
    if (here === shown.length) {
      list.appendChild(nowLine());
    }
  }

  function showWeather(weather) {
    var box = byId("weather");
    if (!weather) {
      box.hidden = true;
      return;
    }
    byId("weather-icon").textContent = weather.icon || "";
    byId("temperature").textContent = weather.temperature + "°";
    byId("sky").textContent = skyLine(weather);
    byId("chip-max").textContent = "↑ " + weather.maximum + "°";
    byId("chip-min").textContent = "↓ " + weather.minimum + "°";
    byId("chip-rain").textContent = "💧 " + weather.rain_chance + "%";
    box.hidden = false;
  }

  function showMeal(meal) {
    var card = byId("meal-card");
    var list = byId("meal-items");
    var view = mealView(meal);
    clear(list);
    card.hidden = !view;
    if (!view) {
      byId("board").classList.remove("has-meal");
      return;
    }
    byId("board").classList.add("has-meal");
    byId("meal-title").textContent = view.title;
    view.rows.forEach(function (row) {
      var item = document.createElement("li");
      item.className = row.className;
      item.textContent = row.text;
      list.appendChild(item);
    });
  }

  function render(data, sentAt, receivedAt) {
    var server = Date.parse(data.now);
    if (!isNaN(server)) {
      offset = server - (sentAt + receivedAt) / 2;
    }
    if (data.quiet) {
      document.documentElement.setAttribute("data-theme", "night");
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
    var away = awayText(data.away);
    byId("away").textContent = away;
    byId("away").hidden = !away;
    showWeather(data.weather);
    upcoming = data.next || null;
    fillToday(data.today);
    showMeal(data.meal);
    var lists = data.lists || {};
    fillList("compras", lists.compras);
    fillList("pendientes", lists.pendientes);
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

  function loadWritable() {
    fetch("/api/people", { cache: "no-store" })
      .then(function (response) {
        return response.ok ? response.json() : { writable: false };
      })
      .then(function (data) {
        writable = Boolean(data.writable);
        showAdders();
        poll();
      })
      .catch(function () {
        writable = false;
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
    wireAdder("compras");
    wireAdder("pendientes");
    tick();
    poll();
    if (readOnly(location.search)) {
      document.body.classList.add("read-only");
    } else {
      loadWritable();
    }
    setInterval(tick, 1000);
    setInterval(poll, POLL_MS);
  });
})();
