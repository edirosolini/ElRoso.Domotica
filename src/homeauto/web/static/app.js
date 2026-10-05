// Agenda de la casa: FullCalendar contra /api/events, con alta, edición y baja de avisos desde un panel.
(function () {
  "use strict";

  var HOUR = { hour: "2-digit", minute: "2-digit", hour12: false };
  var MONTH_VIEW = "dayGridMonth";
  var WIDE = "(min-width: 720px)";
  var MIN_HEIGHT = 480;
  var BOTTOM_GAP = 40;
  var TICK_MS = 60000;
  var TOAST_MS = 2600;

  function pad(number) {
    return number < 10 ? "0" + number : String(number);
  }

  function sameDay(first, second) {
    return first.getFullYear() === second.getFullYear() &&
      first.getMonth() === second.getMonth() &&
      first.getDate() === second.getDate();
  }

  // Si un evento con hora de hoy ya pasó: sonó, terminó o su hora quedó atrás.
  function isPastToday(item, now) {
    if (item.allDay || !item.start || !sameDay(item.start, now)) {
      return false;
    }
    if (item.source === "casa" && item.past) {
      return true;
    }
    return (item.end || item.start).getTime() <= now.getTime();
  }

  // Una fecha en el formato del campo datetime-local, en hora local.
  function toLocalInput(date) {
    return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate()) +
      "T" + pad(date.getHours()) + ":" + pad(date.getMinutes());
  }

  // A qué hora abren semana y día: una antes de la actual.
  function nowScroll(now) {
    return pad(Math.max(0, now.getHours() - 1)) + ":00:00";
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { isPastToday: isPastToday, toLocalInput: toLocalInput, nowScroll: nowScroll };
  }
  if (typeof document === "undefined") {
    return;
  }

  var state = {
    calendar: null,
    writable: false,
    editing: null,
    detailJob: null,
    showPastToday: false,
    todayToggle: null,
    toastTimer: null,
  };

  function byId(id) {
    return document.getElementById(id);
  }

  function clear(element) {
    while (element.firstChild) {
      element.removeChild(element.firstChild);
    }
  }

  function line(tag, text) {
    var element = document.createElement(tag);
    element.textContent = text;
    return element;
  }

  function option(value, text) {
    var element = line("option", text);
    element.value = String(value);
    return element;
  }

  function showProblems(list) {
    var box = byId("problems");
    clear(box);
    list.forEach(function (text) {
      box.appendChild(line("p", text));
    });
    box.hidden = list.length === 0;
  }

  function showLegend(calendars) {
    var legend = byId("legend");
    clear(legend);
    calendars.forEach(function (calendar) {
      var item = document.createElement("li");
      var pill = line("span", calendar.name);
      pill.className = "pill";
      pill.style.setProperty("--c", calendar.color);
      item.appendChild(pill);
      legend.appendChild(item);
    });
  }

  // Un aviso breve abajo de la pantalla, que se va solo.
  function toast(text) {
    var box = byId("toast");
    box.textContent = text;
    box.hidden = false;
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(function () {
      box.hidden = true;
    }, TOAST_MS);
  }

  // Pide JSON a la casa; una respuesta de error se vuelve un Error con su texto.
  function send(method, url, body) {
    var options = {
      method: method,
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      credentials: "same-origin",
    };
    if (body !== undefined) {
      options.body = JSON.stringify(body);
    }
    return fetch(url, options).then(function (response) {
      return response.json().catch(function () {
        return {};
      }).then(function (data) {
        if (!response.ok) {
          throw new Error(data.error || "No pude guardar el cambio.");
        }
        return data;
      });
    });
  }

  // --- lo que ya pasó hoy ---

  function rawItem(raw) {
    var props = raw.extendedProps || {};
    return {
      start: raw.start ? new Date(raw.start) : null,
      end: raw.end ? new Date(raw.end) : null,
      allDay: Boolean(raw.allDay),
      source: props.source,
      past: Boolean(props.past),
    };
  }

  function eventItem(event) {
    return {
      start: event.start,
      end: event.end,
      allDay: event.allDay,
      source: event.extendedProps.source,
      past: Boolean(event.extendedProps.past),
    };
  }

  function folding() {
    return state.calendar !== null && state.calendar.view.type === MONTH_VIEW &&
      !state.showPastToday;
  }

  function showToggle(count) {
    var toggle = state.todayToggle;
    if (!toggle) {
      return;
    }
    toggle.hidden = count === 0;
    toggle.setAttribute("aria-pressed", state.showPastToday ? "true" : "false");
    toggle.title = state.showPastToday
      ? "Ocultar lo que ya pasó hoy"
      : "Mostrar lo que ya pasó hoy (" + count + ")";
  }

  // Oculta en el mes lo que ya pasó hoy, o lo muestra si se tocó «…».
  function applyPastToday() {
    var calendar = state.calendar;
    if (!calendar) {
      return;
    }
    var now = new Date();
    var month = calendar.view.type === MONTH_VIEW;
    var count = 0;
    calendar.batchRendering(function () {
      calendar.getEvents().forEach(function (event) {
        var past = month && isPastToday(eventItem(event), now);
        if (past) {
          count += 1;
        }
        var display = past && !state.showPastToday ? "none" : "block";
        if (event.display !== display) {
          event.setProp("display", display);
        }
      });
    });
    showToggle(count);
  }

  // Repliega lo que pasó y vuelve a pedir los eventos, para ver lo agregado desde otro lado.
  function refresh() {
    if (!state.calendar) {
      return;
    }
    applyPastToday();
    state.calendar.refetchEvents();
  }

  function mountTodayToggle(info) {
    if (!info.isToday || info.view.type !== MONTH_VIEW) {
      return;
    }
    var toggle = line("button", "…");
    toggle.type = "button";
    toggle.className = "past-toggle";
    toggle.hidden = true;
    toggle.addEventListener("click", function (click) {
      click.stopPropagation();
      state.showPastToday = !state.showPastToday;
      applyPastToday();
    });
    // La fila de arriba va en row-reverse: el último hijo queda a la izquierda.
    (info.el.querySelector(".fc-daygrid-day-top") || info.el).appendChild(toggle);
    state.todayToggle = toggle;
  }

  // --- el detalle ---

  function describeWhen(event) {
    var day = event.start.toLocaleDateString("es-AR", {
      weekday: "long", day: "numeric", month: "long",
    });
    if (event.allDay) {
      return day + ", todo el día";
    }
    var text = day + ", " + event.start.toLocaleTimeString("es-AR", HOUR);
    if (event.end) {
      text += " a " + event.end.toLocaleTimeString("es-AR", HOUR);
    }
    return text;
  }

  function openDetail(event) {
    var props = event.extendedProps;
    byId("detail-title").textContent = event.title;
    byId("detail-when").textContent = describeWhen(event);
    var where = props.source === "google" ? "Calendario " + props.calendar : "La casa";
    if (props.location) {
      where += " · " + props.location;
    }
    byId("detail-where").textContent = where;
    var marks = byId("detail-marks");
    clear(marks);
    (props.marks || []).forEach(function (mark) {
      marks.appendChild(line("li", mark));
    });
    state.detailJob = props.source === "casa" && props.job ? props.job : null;
    var editable = state.writable && state.detailJob !== null;
    byId("detail-edit").hidden = !editable;
    byId("detail-delete").hidden = !editable;
    byId("detail").hidden = false;
  }

  function closeDetail() {
    byId("detail").hidden = true;
  }

  function deleteJob() {
    var job = state.detailJob;
    if (job === null || !window.confirm("¿Borrar este aviso? Si repite, se borra la serie entera.")) {
      return;
    }
    send("DELETE", "/api/jobs/" + job).then(function () {
      closeDetail();
      state.calendar.refetchEvents();
      toast("Aviso borrado.");
    }).catch(function (error) {
      closeDetail();
      toast(error.message);
    });
  }

  function editJob() {
    var job = state.detailJob;
    if (job === null) {
      return;
    }
    send("GET", "/api/jobs/" + job).then(function (data) {
      closeDetail();
      openEditor(data, null);
    }).catch(function (error) {
      closeDetail();
      toast(error.message);
    });
  }

  // --- el formulario ---

  function buttonsIn(id) {
    return Array.prototype.slice.call(byId(id).querySelectorAll("button"));
  }

  function press(button, on) {
    button.classList.toggle("on", on);
    if (button.hasAttribute("aria-pressed")) {
      button.setAttribute("aria-pressed", on ? "true" : "false");
    }
  }

  function setType(type) {
    byId("editor-type").value = type;
    buttonsIn("editor-types").forEach(function (button) {
      press(button, button.getAttribute("data-type") === type);
    });
    syncRepeat();
  }

  // Ajusta repetición y días a lo que permite cada tipo.
  function syncRepeat() {
    var type = byId("editor-type").value;
    var repeat = byId("editor-repeat");
    var once = repeat.querySelector('option[value="once"]');
    repeat.disabled = type === "timer";
    once.disabled = type === "reminder";
    if (type === "timer") {
      repeat.value = "once";
    } else if (type === "reminder" && repeat.value === "once") {
      repeat.value = "daily";
    }
    byId("editor-days").hidden = repeat.value !== "weekly";
  }

  function showEditorError(text) {
    var box = byId("editor-error");
    box.textContent = text;
    box.hidden = !text;
  }

  function nextHour() {
    var when = new Date();
    when.setMinutes(0, 0, 0);
    when.setHours(when.getHours() + 1);
    return when;
  }

  function openEditor(job, when) {
    state.editing = job ? job.id : null;
    byId("editor-title").textContent = job ? "Editar aviso #" + job.id : "Nuevo aviso";
    byId("editor-message").value = job ? job.message : "";
    byId("editor-when").value = job ? job.when : toLocalInput(when || nextHour());
    byId("editor-repeat").value = job ? job.repeat : "once";
    var days = job ? job.days : [];
    buttonsIn("editor-days").forEach(function (button) {
      press(button, days.indexOf(parseInt(button.getAttribute("data-day"), 10)) !== -1);
    });
    byId("editor-device").value = job ? job.device : "";
    byId("editor-author-label").hidden = Boolean(job);
    setType(job ? job.type : "alarm");
    showEditorError("");
    byId("editor").hidden = false;
    byId("editor-message").focus();
  }

  function closeEditor() {
    byId("editor").hidden = true;
    state.editing = null;
  }

  function collect() {
    var days = [];
    buttonsIn("editor-days").forEach(function (button) {
      if (button.classList.contains("on")) {
        days.push(parseInt(button.getAttribute("data-day"), 10));
      }
    });
    return {
      type: byId("editor-type").value,
      message: byId("editor-message").value,
      when: byId("editor-when").value,
      repeat: byId("editor-repeat").value,
      days: days,
      device: byId("editor-device").value,
      author: parseInt(byId("editor-author").value, 10),
    };
  }

  function save(submit) {
    submit.preventDefault();
    var button = byId("editor-save");
    var editing = state.editing;
    button.disabled = true;
    var asked = editing === null
      ? send("POST", "/api/jobs", collect())
      : send("PUT", "/api/jobs/" + editing, collect());
    asked.then(function () {
      closeEditor();
      state.calendar.refetchEvents();
      toast(editing === null ? "Aviso guardado." : "Aviso cambiado.");
    }).catch(function (error) {
      showEditorError(error.message);
    }).then(function () {
      button.disabled = false;
    });
  }

  function clickedDay(info) {
    if (!state.writable) {
      return;
    }
    var target = info.jsEvent && info.jsEvent.target;
    if (target && target.closest && target.closest(".past-toggle")) {
      return;
    }
    var when = new Date(info.date.getTime());
    if (info.allDay) {
      when.setHours(8, 0, 0, 0);
    }
    if (when.getTime() <= Date.now()) {
      when = nextHour();
    }
    openEditor(null, when);
  }

  function loadPeople() {
    send("GET", "/api/people").then(function (data) {
      state.writable = Boolean(data.writable);
      var author = byId("editor-author");
      clear(author);
      (data.people || []).forEach(function (person) {
        author.appendChild(option(person.chat_id, person.name));
      });
      var device = byId("editor-device");
      (data.devices || []).forEach(function (alias) {
        device.appendChild(option(alias, alias));
      });
      byId("new-job").hidden = !state.writable;
    }).catch(function () {
      state.writable = false;
    });
  }

  function initialDate() {
    var month = new URLSearchParams(window.location.search).get("m") || "";
    return /^\d{4}-\d{2}$/.test(month) ? month + "-01" : undefined;
  }

  function closeOnBackdrop(id, close) {
    byId(id).addEventListener("click", function (click) {
      if (click.target === click.currentTarget) {
        close();
      }
    });
  }

  // El título del período y la vista marcada en el selector.
  // En pantalla ancha el calendario ocupa el alto de la ventana y cada día muestra lo que entra.
  function fitHeight(calendar) {
    var wide = window.matchMedia(WIDE).matches;
    if (!wide) {
      calendar.setOption("height", "auto");
      calendar.setOption("dayMaxEvents", 5);
      return;
    }
    var top = byId("calendar").getBoundingClientRect().top + window.pageYOffset;
    calendar.setOption("height", Math.max(MIN_HEIGHT, window.innerHeight - top - BOTTOM_GAP));
    calendar.setOption("dayMaxEvents", true);
  }

  function showPeriod(info) {
    byId("title").textContent = info.view.title;
    buttonsIn("views").forEach(function (button) {
      press(button, button.getAttribute("data-view") === info.view.type);
    });
  }

  function wireBar(calendar) {
    byId("prev").addEventListener("click", function () {
      calendar.prev();
    });
    byId("next").addEventListener("click", function () {
      calendar.next();
    });
    byId("today").addEventListener("click", function () {
      calendar.today();
    });
    buttonsIn("views").forEach(function (button) {
      button.addEventListener("click", function () {
        calendar.setOption("scrollTime", nowScroll(new Date()));
        calendar.changeView(button.getAttribute("data-view"));
      });
    });
  }

  // Le pasa al evento su color para la piel del tablero.
  function paintEvent(info) {
    var color = info.event.backgroundColor || info.event.borderColor;
    info.el.classList.add("ev");
    if (color) {
      info.el.style.setProperty("--ev", color);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    byId("detail-close").addEventListener("click", closeDetail);
    byId("detail-edit").addEventListener("click", editJob);
    byId("detail-delete").addEventListener("click", deleteJob);
    byId("editor-cancel").addEventListener("click", closeEditor);
    byId("editor-form").addEventListener("submit", save);
    byId("editor-repeat").addEventListener("change", syncRepeat);
    buttonsIn("editor-types").forEach(function (button) {
      button.addEventListener("click", function () {
        setType(button.getAttribute("data-type"));
      });
    });
    buttonsIn("editor-days").forEach(function (button) {
      button.addEventListener("click", function () {
        press(button, !button.classList.contains("on"));
      });
    });
    byId("new-job").addEventListener("click", function () {
      openEditor(null, null);
    });
    closeOnBackdrop("detail", closeDetail);
    closeOnBackdrop("editor", closeEditor);

    var calendar = new FullCalendar.Calendar(byId("calendar"), {
      locale: "es",
      timeZone: "local",
      initialView: MONTH_VIEW,
      initialDate: initialDate(),
      headerToolbar: false,
      footerToolbar: false,
      height: "auto",
      nowIndicator: true,
      scrollTime: nowScroll(new Date()),
      editable: false,
      dayMaxEvents: 5,
      navLinks: true,
      eventTimeFormat: HOUR,
      slotLabelFormat: HOUR,
      events: {
        url: "/api/events",
        failure: function () {
          showProblems(["No pude leer la agenda."]);
        },
      },
      eventSourceSuccess: function (content) {
        showProblems(content.problems || []);
        showLegend(content.calendars || []);
        var now = new Date();
        var fold = folding();
        return (content.events || []).map(function (raw) {
          raw.display = "block";
          if (fold && isPastToday(rawItem(raw), now)) {
            raw.display = "none";
          }
          return raw;
        });
      },
      eventsSet: function () {
        applyPastToday();
      },
      datesSet: function (info) {
        showPeriod(info);
        applyPastToday();
      },
      eventDidMount: paintEvent,
      dayCellDidMount: mountTodayToggle,
      dateClick: clickedDay,
      eventClick: function (info) {
        info.jsEvent.preventDefault();
        openDetail(info.event);
      },
    });
    state.calendar = calendar;
    wireBar(calendar);
    calendar.render();
    fitHeight(calendar);
    window.addEventListener("resize", function () {
      fitHeight(calendar);
    });
    loadPeople();
    setInterval(refresh, TICK_MS);
  });
})();
