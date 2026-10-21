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

  // A quién se puede elegir: las personas del padrón o, sin padrón, los chats.
  function whoOptions(data) {
    var persons = (data && data.persons) || [];
    var options = [];
    var i;
    if (persons.length) {
      for (i = 0; i < persons.length; i++) {
        options.push({ key: "p:" + persons[i].id,
          label: persons[i].name + (persons[i].chat_id === null ? " (sin Telegram)" : ""),
          chat_id: persons[i].chat_id });
      }
      return options;
    }
    var people = (data && data.people) || [];
    for (i = 0; i < people.length; i++) {
      options.push({ key: "c:" + people[i].chat_id, label: people[i].name });
    }
    return options;
  }

  // El guardado si sigue; uno viejo, solo el número de chat, por su chat; si no, el primero.
  function pickWho(options, saved) {
    var i;
    var chat = String(saved).replace(/^c:/, "");
    for (i = 0; i < options.length; i++) {
      if (options[i].key === String(saved)) {
        return options[i].key;
      }
    }
    for (i = 0; i < options.length; i++) {
      var own = options[i].key.indexOf("c:") === 0 ? options[i].key.slice(2) : options[i].chat_id;
      if (own !== null && own !== undefined && String(own) === chat) {
        return options[i].key;
      }
    }
    return options.length ? options[0].key : null;
  }

  // El cuerpo del POST: un botón viaja como data, lo escrito suelto como text.
  function commandBody(who, value, free) {
    var id = parseInt(who.slice(2), 10);
    var body = who.indexOf("p:") === 0 ? { person_id: id } : { chat_id: id };
    body[free ? "text" : "data"] = value;
    return body;
  }

  function liveUrl(who) {
    if (who.indexOf("p:") === 0) {
      return "/api/live?person=" + encodeURIComponent(who.slice(2));
    }
    return "/api/live?chat=" + encodeURIComponent(who.slice(2));
  }

  // Un chat con el nombre visto en Telegram o, si no escribió, con sus últimos cuatro dígitos.
  function chatLabel(chat) {
    if (chat.seen) {
      return chat.seen + " (" + chat.chat_id + ")";
    }
    return "Todavía no escribió (·" + String(Math.abs(chat.chat_id)).slice(-4) + ")";
  }

  // El comando de un formulario; null si el dato es obligatorio y está vacío.
  function formCommand(verb, need, devices, text) {
    if (need && !String(text || "").replace(/\s+/g, "")) {
      return null;
    }
    return targeted(verb, devices, text);
  }

  // Los chats que esa persona puede tomar: los de nadie y el suyo.
  function freeChats(chats, persons, personId) {
    var free = [];
    for (var i = 0; i < (chats || []).length; i++) {
      var taken = false;
      for (var j = 0; j < (persons || []).length; j++) {
        if (persons[j].chat_id === chats[i].chat_id && persons[j].id !== personId) {
          taken = true;
        }
      }
      if (!taken) {
        free.push(chats[i]);
      }
    }
    return free;
  }

  // El cuerpo del alta de una persona; un chat vacío es sin Telegram.
  function personBody(name, chat) {
    return { name: String(name).replace(/^\s+|\s+$/g, ""),
      chat_id: chat === "" ? null : parseInt(chat, 10) };
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

  // La cola «· para X» de lo que es de alguien; vacía si no.
  function forSuffix(item) {
    return item.for ? " · para " + item.for : "";
  }

  // Lo urgente en el orden en que se muestra, cada uno con sus botones.
  function urgentItems(live) {
    var items = [];
    var now = live.now;
    var i;
    var ringing = live.ringing || [];
    for (i = 0; i < ringing.length; i++) {
      items.push({ kind: "ringing", title: "⏰ " + ringing[i].message,
        meta: "Sonando " + sinceText(ringing[i].since, now) + forSuffix(ringing[i]),
        actions: ringing[i].actions });
    }
    var awaiting = live.awaiting || [];
    for (i = 0; i < awaiting.length; i++) {
      items.push({ kind: "awaiting", title: "🔔 " + awaiting[i].message,
        meta: "Espera su «Hecho» · sonó " + sinceText(awaiting[i].since, now) +
          forSuffix(awaiting[i]),
        actions: awaiting[i].actions });
    }
    if (live.snooze) {
      items.push({ kind: "snooze", title: "↻ " + live.snooze.message,
        meta: "Sonó " + sinceText(live.snooze.since, now) + " · se puede posponer" +
          forSuffix(live.snooze),
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

  // Si lo urgente no tiene nada más que el silencio.
  function isCalm(items) {
    for (var i = 0; i < items.length; i++) {
      if (items[i].kind !== "quiet") {
        return false;
      }
    }
    return true;
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
      targeted: targeted, whoOptions: whoOptions, pickWho: pickWho, commandBody: commandBody,
      liveUrl: liveUrl, chatLabel: chatLabel, freeChats: freeChats, personBody: personBody,
      sinceText: sinceText, quietTitle: quietTitle, urgentItems: urgentItems,
      statusText: statusText, formCommand: formCommand, isCalm: isCalm,
    };
  }
  if (typeof document === "undefined") {
    return;
  }

  // La clave de quien eligió el dispositivo: «p:<persona>» o «c:<chat>».
  var who = null;
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
    byId("urgent-card").classList.toggle("calm", isCalm(items));
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
    if (who === null) {
      return;
    }
    fetch(liveUrl(who), { cache: "no-store" })
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
    if (who === null) {
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
      body: JSON.stringify(commandBody(who, value, free)),
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
        var devices = node.getAttribute("data-target") ? checkedDevices() : [];
        var command = formCommand(node.getAttribute("data-verb"), Boolean(node.getAttribute("data-need")),
          devices, text);
        if (command === null) {
          input.focus();
          return;
        }
        send(command, false);
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

  // Marca el chip del equipo según su casilla.
  function markDevice(label, check) {
    return function () {
      label.classList.toggle("on", check.checked);
    };
  }

  function fillDevices(devices) {
    var box = byId("devices");
    clear(box);
    for (var i = 0; i < (devices || []).length; i++) {
      var label = element("label", "device");
      var check = document.createElement("input");
      check.type = "checkbox";
      check.value = devices[i];
      check.addEventListener("change", markDevice(label, check));
      label.appendChild(check);
      label.appendChild(element("span", "", devices[i]));
      box.appendChild(label);
    }
  }

  function option(value, label) {
    var node = element("option", "", label);
    node.value = value;
    return node;
  }

  function fillWho(options) {
    var select = byId("who");
    clear(select);
    for (var i = 0; i < options.length; i++) {
      select.appendChild(option(options[i].key, options[i].label));
    }
    who = pickWho(options, readSaved());
    if (who !== null) {
      select.value = who;
    }
  }

  // Llena un desplegable con «Sin Telegram» y los chats que esa persona puede tomar.
  function fillChats(select, data, personId, selected) {
    clear(select);
    select.appendChild(option("", "Sin Telegram"));
    var free = freeChats(data.chats, data.persons, personId);
    for (var i = 0; i < free.length; i++) {
      select.appendChild(option(String(free[i].chat_id), chatLabel(free[i])));
    }
    select.value = selected === null || selected === undefined ? "" : String(selected);
  }

  // Escribe en el padrón y vuelve a leer la gente; una negativa se muestra con su motivo.
  function writePerson(method, path, body) {
    var request = { method: method, headers: { "Content-Type": "application/json" } };
    if (body) {
      request.body = JSON.stringify(body);
    }
    fetch(path, request)
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, data: data };
        });
      })
      .then(function (result) {
        if (!result.ok) {
          showAnswer("🔴 " + (result.data.error || "No pude guardarlo."), []);
        }
        loadPeople();
      })
      .catch(function () {
        showAnswer("🔴 " + LOST, []);
      });
  }

  function personRow(person, data) {
    var path = "/api/persons/" + person.id;
    var row = element("li", "person");
    row.appendChild(element("span", "person-name", person.name));
    var select = document.createElement("select");
    select.setAttribute("aria-label", "Telegram de " + person.name);
    fillChats(select, data, person.id, person.chat_id);
    select.addEventListener("change", function () {
      writePerson("PUT", path, { chat_id: select.value === "" ? null : parseInt(select.value, 10) });
    });
    row.appendChild(select);
    var actions = element("div", "person-actions");
    var rename = element("button", "", "Renombrar");
    rename.type = "button";
    rename.addEventListener("click", function () {
      var name = window.prompt("Nuevo nombre de " + person.name, person.name);
      if (name !== null && name !== person.name) {
        writePerson("PUT", path, { name: name });
      }
    });
    actions.appendChild(rename);
    var remove = element("button", "danger", "Borrar");
    remove.type = "button";
    remove.addEventListener("click", function () {
      if (window.confirm("¿Borrar a " + person.name + " del padrón?")) {
        writePerson("DELETE", path, null);
      }
    });
    actions.appendChild(remove);
    row.appendChild(actions);
    return row;
  }

  function renderPersons(data) {
    byId("persons-card").hidden = !data.writable;
    if (!data.writable) {
      return;
    }
    var list = byId("persons");
    clear(list);
    var persons = data.persons || [];
    for (var i = 0; i < persons.length; i++) {
      list.appendChild(personRow(persons[i], data));
    }
    fillChats(byId("person-chat"), data, null, null);
  }

  function wirePersons() {
    var form = byId("person-add");
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var input = byId("person-name");
      if (!input.value.replace(/\s+/g, "")) {
        input.focus();
        return;
      }
      writePerson("POST", "/api/persons", personBody(input.value, byId("person-chat").value));
      input.value = "";
    });
  }

  function loadPeople() {
    fetch("/api/people", { cache: "no-store" })
      .then(function (response) {
        return response.ok ? response.json() : { writable: false, people: [], devices: [] };
      })
      .then(function (data) {
        fillDevices(data.devices);
        renderPersons(data);
        var options = whoOptions(data);
        if (!data.writable || !options.length) {
          showProblem("Sin ALLOWED_CHAT_IDS la pantalla no maneja la casa.");
          return;
        }
        fillWho(options);
        poll();
      })
      .catch(function () {
        showProblem(LOST);
      });
  }

  document.addEventListener("DOMContentLoaded", function () {
    byId("who").addEventListener("change", function () {
      who = byId("who").value;
      save(who);
      poll();
    });
    wireCommands();
    wireFree();
    wirePersons();
    loadPeople();
    setInterval(poll, POLL_MS);
  });
})();
