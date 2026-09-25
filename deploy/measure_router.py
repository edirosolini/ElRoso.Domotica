"""Mide el prompt del router contra el endpoint real.

Corre adentro del contenedor: la clave sale de la config y nunca de un argumento.
"""

import sys
import time

sys.path.insert(0, "/opt/domotica/src")

from homeauto.config import Config
from homeauto.polish import GoogleModel
from homeauto.route import Router

# Entre llamada y llamada, para no chocar con el límite por minuto del free tier.
PAUSE = 4

# mensaje, comando esperado, fragmento que tiene que estar en el argumento.
CASES = (
    ("poneme un timer de diez minutos para sacar la pizza", "timer", "10m"),
    ("avisame en media hora que saque la ropa", "timer", "30m"),
    ("despertame mañana a las siete y media", "alarma", "7:30"),
    ("poné una alarma todos los días a las 7:30 para levantarse", "alarma", "7:30"),
    ("qué tengo programado", "lista", ""),
    ("cancelá el 3", "cancelar", "3"),
    ("posponé la alarma cinco minutos", "posponer", "5m"),
    ("callate dos horas", "silencio", "2h"),
    ("podés hablar de nuevo", "hablar", ""),
    ("bajá el volumen a 30", "volumen", "30"),
    ("pará lo que está sonando", "parar", ""),
    ("apagá la tele del comedor", "apagar", ""),
    ("cómo está el clima", "clima", ""),
    ("qué tengo en la agenda", "agenda", ""),
    ("cómo están los servicios", "estado", ""),
    ("qué equipos tenés", "equipos", ""),
    ("usá el comedor de ahora en más", "usar", "comedor"),
    ("cuántos goles hizo Messi", "preguntar", "Messi"),
    ("decí que ya llegué", "decir", "que ya llegué"),
    ("decile a todos que la comida está lista", "decir", "la comida está lista"),
    ("avisá en el comedor que salgo en cinco minutos", "decir", "salgo en cinco minutos"),
    ("llamá a los chicos a comer", "llamar", "comer"),
    ("llamar a todos a cenar", "llamar", "cenar"),
    ("cuánto es 15 por 4", "calcular", "15"),
    ("cuántos kilómetros son 5 millas", "calcular", "millas"),
    ("agregá leche y pan a la lista de compras", "agregar", "leche"),
    ("anotá en pendientes que tengo que llamar al plomero", "agregar", "plomero"),
    ("qué falta comprar", "compras", ""),
    ("qué tengo pendiente", "pendientes", ""),
    ("sacá el 2 de la lista de compras", "sacar", "2"),
    ("traducí hola al inglés", "traducir", "hola"),
)


def main() -> int:
    config = Config.from_file("/etc/domotica/domotica.env")
    router = Router(model=GoogleModel(api_key=config.llm_api_key, model=config.llm_model))
    print(f"modelo: {config.llm_model}\n")

    good = 0
    payload_checks = 0
    payload_good = 0
    for message, expected, fragment in CASES:
        started = time.time()
        try:
            decision = router.route(message)
            got = decision.command or ("(pregunta)" if decision.is_question else "(nada)")
            argument = decision.argument
        except Exception as exc:  # noqa: BLE001
            got, argument = f"ERROR {type(exc).__name__}", str(exc)[:60]
        elapsed = time.time() - started

        ok = got == expected
        good += ok
        mark = "ok  " if ok else "FALLA"
        if fragment:
            payload_checks += 1
            in_payload = fragment.lower() in (argument or "").lower()
            payload_good += in_payload
            note = "" if in_payload else f"  ← falta «{fragment}»"
        else:
            note = ""
        print(f"{mark} {message[:46]:48} → {got:12} «{argument}»{note}  [{elapsed:.1f}s]")
        time.sleep(PAUSE)

    print(f"\ncomandos: {good}/{len(CASES)}")
    print(f"payloads: {payload_good}/{payload_checks}")
    return 0 if good == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
