// Diálogos propios de la casa: confirmar y pedir un dato, con letra grande y el foco adentro.
(function () {
  "use strict";

  var DEFAULTS = {
    confirm: { yes: "Sí, borrar", no: "No" },
    ask: { yes: "Guardar", no: "No" },
  };

  // Las etiquetas de los botones: las por defecto del tipo pisadas por las que se pasan.
  function labels(kind, given) {
    var base = DEFAULTS[kind];
    return {
      yes: (given && given.yes) || base.yes,
      no: (given && given.no) || base.no,
    };
  }

  // Qué hace una tecla: «no» con Escape, «tab» con Tab, null el resto.
  function keyAction(key) {
    if (key === "Escape" || key === "Esc") {
      return "no";
    }
    return key === "Tab" ? "tab" : null;
  }

  // El índice del próximo elemento con foco, dando la vuelta en los dos sentidos.
  function nextFocus(count, index, back) {
    if (index < 0) {
      return back ? count - 1 : 0;
    }
    return (index + (back ? count - 1 : 1)) % count;
  }

  // La función que llama a fn solo la primera vez.
  function once(fn) {
    var done = false;
    return function (value) {
      if (done) {
        return;
      }
      done = true;
      fn(value);
    };
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { labels: labels, keyAction: keyAction, nextFocus: nextFocus, once: once };
  }
  if (typeof document === "undefined") {
    return;
  }

  var open = false;
  var count = 0;

  function element(tag, className, text) {
    var node = document.createElement(tag);
    node.className = className;
    if (text) {
      node.textContent = text;
    }
    return node;
  }

  // Arma el diálogo, lo muestra y llama a done con el valor de «Sí» o con null.
  function show(text, names, initial, max, done) {
    if (open) {
      return;
    }
    open = true;
    count += 1;
    var opener = document.activeElement;
    var wrap = element("div", "dialog-wrap");
    var box = element("form", "dialog");
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    box.setAttribute("aria-labelledby", "dialog-text-" + count);
    box.noValidate = true;
    var message = element("p", "dialog-text");
    message.id = "dialog-text-" + count;
    message.textContent = text;
    box.appendChild(message);
    var input = null;
    if (initial !== null) {
      input = element("input", "dialog-input");
      input.type = "text";
      if (max) {
        input.maxLength = max;
      }
      input.autocomplete = "off";
      input.value = initial;
      input.setAttribute("aria-labelledby", message.id);
      box.appendChild(input);
    }
    var row = element("div", "dialog-actions");
    var no = element("button", "btn secondary", names.no);
    no.type = "button";
    var yes = element("button", "btn primary", names.yes);
    yes.type = "submit";
    row.appendChild(no);
    row.appendChild(yes);
    box.appendChild(row);
    wrap.appendChild(box);

    var focusable = input ? [input, no, yes] : [no, yes];

    var finish = once(function (value) {
      open = false;
      document.removeEventListener("keydown", onKey, true);
      document.removeEventListener("focusin", onFocus, true);
      wrap.parentNode.removeChild(wrap);
      if (opener && opener.focus && document.body.contains(opener)) {
        opener.focus();
      }
      done(value);
    });

    function onKey(event) {
      var action = keyAction(event.key);
      if (action === "no") {
        event.preventDefault();
        finish(null);
      } else if (action === "tab") {
        event.preventDefault();
        focusable[nextFocus(focusable.length, focusable.indexOf(document.activeElement), event.shiftKey)].focus();
      }
    }

    // El foco que se escapa del diálogo vuelve adentro.
    function onFocus(event) {
      if (!box.contains(event.target)) {
        focusable[0].focus();
      }
    }

    no.addEventListener("click", function () {
      finish(null);
    });
    box.addEventListener("submit", function (event) {
      event.preventDefault();
      finish(input ? input.value : true);
    });
    wrap.addEventListener("click", function (event) {
      if (event.target === wrap) {
        finish(null);
      }
    });
    document.addEventListener("keydown", onKey, true);
    document.addEventListener("focusin", onFocus, true);
    document.body.appendChild(wrap);
    if (input) {
      input.focus();
      input.select();
    } else {
      no.focus();
    }
  }

  window.HouseDialog = {
    // Pregunta text con «Sí»/«No»; callback recibe true o false.
    confirm: function (text, given, callback) {
      show(text, labels("confirm", given), null, 0, function (value) {
        callback(value === true);
      });
    },
    // Pide un dato con su valor inicial y un tope opcional (given.max); callback recibe lo escrito o null.
    ask: function (text, initial, given, callback) {
      show(text, labels("ask", given), String(initial || ""), (given && given.max) || 0, callback);
    },
  };
})();
