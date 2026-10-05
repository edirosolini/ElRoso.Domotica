// Agenda de la casa: FullCalendar contra /api/events, de solo lectura.
(function () {
  "use strict";

  var HOUR = { hour: "2-digit", minute: "2-digit", hour12: false };

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

  function showProblems(list) {
    var box = document.getElementById("problems");
    clear(box);
    list.forEach(function (text) {
      box.appendChild(line("p", text));
    });
    box.hidden = list.length === 0;
  }

  function showLegend(calendars) {
    var legend = document.getElementById("legend");
    clear(legend);
    calendars.forEach(function (calendar) {
      var item = line("li", calendar.name);
      var swatch = document.createElement("span");
      swatch.className = "swatch";
      swatch.style.backgroundColor = calendar.color;
      item.insertBefore(swatch, item.firstChild);
      legend.appendChild(item);
    });
  }

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
    document.getElementById("detail-title").textContent = event.title;
    document.getElementById("detail-when").textContent = describeWhen(event);
    var where = props.source === "google" ? "Calendario " + props.calendar : "La casa";
    if (props.location) {
      where += " · " + props.location;
    }
    document.getElementById("detail-where").textContent = where;
    var marks = document.getElementById("detail-marks");
    clear(marks);
    (props.marks || []).forEach(function (mark) {
      marks.appendChild(line("li", mark));
    });
    document.getElementById("detail").hidden = false;
  }

  function closeDetail() {
    document.getElementById("detail").hidden = true;
  }

  function initialDate() {
    var month = new URLSearchParams(window.location.search).get("m") || "";
    return /^\d{4}-\d{2}$/.test(month) ? month + "-01" : undefined;
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("detail-close").addEventListener("click", closeDetail);
    document.getElementById("detail").addEventListener("click", function (click) {
      if (click.target === click.currentTarget) {
        closeDetail();
      }
    });

    var narrow = window.matchMedia("(max-width: 700px)").matches;
    var calendar = new FullCalendar.Calendar(document.getElementById("calendar"), {
      locale: "es",
      timeZone: "local",
      initialView: "dayGridMonth",
      initialDate: initialDate(),
      headerToolbar: narrow
        ? { left: "prev,next", center: "title", right: "today" }
        : { left: "prev,next today", center: "title", right: "dayGridMonth,timeGridWeek,timeGridDay" },
      footerToolbar: narrow ? { center: "dayGridMonth,timeGridWeek,timeGridDay" } : false,
      height: "auto",
      nowIndicator: true,
      editable: false,
      dayMaxEvents: true,
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
        return content.events || [];
      },
      eventClick: function (info) {
        info.jsEvent.preventDefault();
        openDetail(info.event);
      },
    });
    calendar.render();
  });
})();
