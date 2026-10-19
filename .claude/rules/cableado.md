---
paths:
  - "src/homeauto/main.py"
  - "tests/test_main_wiring.py"
---

# Cableado

## Cableado

`main()` arma todo y es la parte sin tests unitarios, así que **tres bugs llegaron al
contenedor por ahí**: una función renombrada, una variable usada antes de existir, y
`build_polisher` devolviendo el objeto `Polisher` donde el resto esperaba algo llamable — el
servicio arrancaba perfecto y reventaba con `TypeError` recién cuando alguien pedía `/clima`.
`tests/test_main_wiring.py` ejecuta el cableado completo con dobles. Si se agrega una pieza
nueva al arranque, va también un caso ahí.

🔴 **Un doble que no se parece a lo real no prueba nada.** El caso del pulido existía y pasaba:
inyectaba un `object()` como centinela y verificaba que llegara a destino. Como el centinela
tampoco era llamable, el test tenía exactamente el mismo bug que el código. **Los dobles del
cableado tienen que poder usarse como lo que reemplazan**, no solo viajar hasta su lugar.

Las dependencias se construyen antes que quienes las usan; el archivo se lee de arriba hacia
abajo en ese orden a propósito.
