// Pantalla de control: lo urgente arriba, los comandos de Telegram en paneles y texto libre.
(function () {
  "use strict";

  var POLL_MS = 5000;
  var SAVED = "casa.chat";
  var WORKING = "⏳ Procesando…";
  var LOST = "Sin conexión con la casa.";

  // El comando con los equipos tildados adelante: «decir en comedor,recamara hola».
  function targeted(verb, devices, text) {
    var parts = [verb];
    if (devices && devices.length) {
      parts.push("en " + devices.join(","));
    }
    var rest = (text || "").replace(/^\s+|\s+$/g, "");
    if (rest) {
      parts.push(rest);
    }
    return parts.join(" ");
  }

  // El chat guardado si sigue siendo de la casa; si no, el primero; null sin gente.
  function pickChat(people, saved) {
    var list = people || [];
    for (var i = 0; i < list.length; i++) {
      if (String(list[i].chat_id) === String(saved)) {
        return list[i].chat_id;
      }
    }
    return list.length ? list[0].chat_id : null;
  }

  // El cuerpo del POST: un botón viaja como data, lo escrito suelto como text.
  function commandBody(chat, value, free) {
    var body = { chat_id: chat };
    body[free ? "text" : "data"] = value;
    return body;
  }

  function liveUrl(chat) {
    return "/api/live?chat=" + encodeURIComponent(String(chat));
  }

  // Cuánto pasó desde since, dicho corto.
  function sinceText(since, now) {
    var minutes = Math.floor((Date.parse(now) - Date.parse(since)) / 60000);
    if (isNaN(minutes) || minutes < 1) {
      return "recién";
    }
    if (minutes < 60) {
      return "hace " + minutes + " min";
    }
    return "hace " + Math.floor(minutes / 60) + " h";
  }

  function quietTitle(quiet) {
    if (!quiet) {
      return "";
    }
    if (quiet.away_until) {
      return "🧳 " + quiet.reason;
    }
    if (quiet.quiet) {
      return "🤫 " + quiet.reason;
    }
    return "🔊 La casa habla";
  }

  // Lo urgente en el orden en que se muestra, cada uno con sus botones.
  function urgentItems(live) {
    var items = [];
    var now = live.now;
    var i;
    var ringing = live.ringing || [];
    for (i = 0; i < ringing.length; i++) {
      items.push({ kind: "ringing", title: "⏰ " + ringing[i].message,
        meta: "Sonando " + sinceText(ringing[i].since, now), actions: ringing[i].actions });
    }
    var awaiting = live.awaiting || [];
    for (i = 0; i < awaiting.length; i++) {
      items.push({ kind: "awaiting", title: "🔔 " + awaiting[i].message,
        meta: "Espera su «Hecho» · sonó " + sinceText(awaiting[i].since, now),
        actions: awaiting[i].actions });
    }
    if (live.snooze) {
      items.push({ kind: "snooze", title: "↻ " + live.snooze.message,
        meta: "Sonó " + sinceText(live.snooze.since, now) + " · se puede posponer",
        actions: live.snooze.actions });
    }
    var outages = live.outages || [];
    for (i = 0; i < outages.length; i++) {
      items.push({ kind: "outage", title: "🚨 " + outages[i].name + " no responde",
        meta: "Caído " + sinceText(outages[i].since, now), actions: outages[i].actions });
    }
    if (live.quiet) {
      items.push({ kind: "quiet", title: quietTitle(live.quiet), meta: "",
        actions: live.quiet.actions });
    }
    return items;
  }

  function statusText(status) {
    var parts = [];
    for (var i = 0; i < (status || []).length; i++) {
      parts.push((status[i].up ? "✅ " : "🔴 ") + status[i].name);
    }
    return parts.join(" · ");
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      targeted: targeted, pickChat: pickChat, commandBody: commandBody, liveUrl: liveUrl,
      sinceText: sinceText, quietTitle: quietTitle, urgentItems: urgentItems,
      statusText: statusText,
    };
  }
  if (typeof document === "undefined") {
    return;
  }

  var chat = null;
  var busy = false;

  function byId(id) {
    return document.getElementById(id);
  }

  function readSaved() {
    try {
      return window.localStorage.getItem(SAVED);
    } catch (error) {
      return null;
    }
  }

  function save(value) {
    try {
      window.localStorage.setItem(SAVED, String(value));
    } catch (error) {
      return;
    }
  }

  function clear(node) {
    while (node.firstChild) {
      node.removeChild(node.firstChild);
    }
  }

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) {
      node.className = className;
    }
    if (text) {
      node.textContent = text;
    }
    return node;
  }

  function buttonsFor(actions) {
    var row = element("div", "actions");
    for (var i = 0; i < (actions || []).length; i++) {
      row.appendChild(actionButton(actions[i]));
    }
    return row;
  }

  function actionButton(action) {
    var button = element("button", "action", action.label);
    button.type = "button";
    button.addEventListener("click", function () {
      send(action.data, false);
    });
    return button;
  }

  function showProblem(text) {
    var problems = byId("problems");
    problems.textContent = text || "";
    problems.hidden = !text;
  }

  function renderLive(live) {
    var list = byId("urgent");
    clear(list);
    var items = urgentItems(live);
    for (var i = 0; i < items.length; i++) {
      var row = element("li", "urgent-item " + items[i].kind);
      var text = element("div", "urgent-text");
      text.appendChild(element("div", "urgent-title", items[i].title));
      if (items[i].meta) {
        text.appendChild(element("div", "urgent-meta", items[i].meta));
      }
      row.appendChild(text);
      row.appendChild(buttonsFor(items[i].actions));
      list.appendChild(row);
    }
    byId("status").textContent = statusText(live.status);
    showProblem("");
  }

  function poll() {
    if (chat === null) {
      return;
    }
    fetch(liveUrl(chat), { cache: "no-store" })
      .then(function (response) {
        if (!response.ok) {
          throw new Error(String(response.status));
        }
        return response.json();
      })
      .then(renderLive)
      .catch(function () {
        showProblem(LOST);
      });
  }

  function showAnswer(text, actions) {
    var answer = byId("answer");
    clear(answer);
    var body = element("div", "answer-text");
    body.textContent = text;
    answer.appendChild(body);
    answer.appendChild(buttonsFor(actions));
    answer.hidden = false;
  }

  function setBusy(value) {
    busy = value;
    var buttons = document.querySelectorAll("button.action, .cmd button, button.cmd");
    for (var i = 0; i < buttons.length; i++) {
      buttons[i].disabled = value;
    }
  }

  // Manda el comando y muestra la respuesta, sin cortar el pedido por tiempo.
  function send(value, free) {
    if (chat === null) {
      showAnswer("Elegí quién sos.", []);
      return;
    }
    if (busy) {
      return;
    }
    setBusy(true);
    showAnswer(WORKING, []);
    fetch("/api/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(commandBody(chat, value, free)),
    })
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, data: data };
        });
      })
      .then(function (result) {
        if (result.ok) {
          showAnswer(result.data.text, result.data.actions);
        } else {
          showAnswer("🔴 " + (result.data.error || "No pude hacerlo."), []);
        }
      })
      .catch(function () {
        showAnswer("🔴 " + LOST, []);
      })
      .then(function () {
        setBusy(false);
        poll();
      });
  }

  function checkedDevices() {
    var boxes = byId("devices").querySelectorAll("input:checked");
    var names = [];
    for (var i = 0; i < boxes.length; i++) {
      names.push(boxes[i].value);
    }
    return names;
  }

  // Cada .cmd es un botón o un formulario con data-verb; data-target suma los equipos.
  function commandOf(node, text) {
    var devices = node.getAttribute("data-target") ? checkedDevices() : [];
    return targeted(node.getAttribute("data-verb"), devices, text);
  }

  function wireCommands() {
    var nodes = document.querySelectorAll(".cmd");
    for (var i = 0; i < nodes.length; i++) {
      wireCommand(nodes[i]);
    }
  }

  function wireCommand(node) {
    if (node.tagName === "FORM") {
      node.addEventListener("submit", function (event) {
        event.preventDefault();
        var input = node.querySelector("input, textarea");
        var text = input ? input.value : "";
        if (node.getAttribute("data-need") && !text.replace(/\s+/g, "")) {
          input.focus();
          return;
        }
        send(commandOf(node, text), false);
        if (input && !node.getAttribute("data-keep")) {
          input.value = "";
        }
      });
      return;
    }
    node.addEventListener("click", function () {
      send(commandOf(node, ""), false);
    });
  }

  function wireFree() {
    var form = byId("free");
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var input = byId("free-text");
      if (!input.value.replace(/\s+/g, "")) {
        return;
      }
      send(input.value, true);
      input.value = "";
    });
  }

  function fillDevices(devices) {
    var box = byId("devices");
    clear(box);
    for (var i = 0; i < (devices || []).length; i++) {
      var label = element("label", "device");
      var check = document.createElement("input");
      check.type = "checkbox";
      check.value = devices[i];
      label.appendChild(check);
      label.appendChild(element("span", "", devices[i]));
      box.appendChild(label);
    }
  }

  function fillPeople(people) {
    var select = byId("who");
    clear(select);
    for (var i = 0; i < people.length; i++) {
      var option = element("option", "", people[i].name);
      option.value = String(people[i].chat_id);
      select.appendChild(option);
    }
    chat = pickChat(people, readSaved());
    if (chat !== null) {
      select.value = String(chat);
    }
  }

  function loadPeople() {
    fetch("/api/people", { cache: "no-store" })
      .then(function (response) {
        return response.ok ? response.json() : { writable: false, people: [], devices: [] };
      })
      .then(function (data) {
        fillDevices(data.devices);
        if (!data.writable || !(data.people || []).length) {
          showProblem("Sin ALLOWED_CHAT_IDS la pantalla no maneja la casa.");
          return;
        }
        fillPeople(data.people);
        poll();
      })
      .catch(function () {
        showProblem(LOST);
      });
  }

  document.addEventListener("DOMContentLoaded", function () {
    byId("who").addEventListener("change", function () {
      chat = parseInt(byId("who").value, 10);
      save(chat);
      poll();
    });
    wireCommands();
    wireFree();
    loadPeople();
    setInterval(poll, POLL_MS);
  });
})();
