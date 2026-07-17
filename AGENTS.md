# Instrucciones Compartidas Para Agentes

## Lecturas Obligatorias

1. `08-context/system-policy.md`
2. `08-context/source-of-truth.md`
3. `config/workspace.local.json`, si existe
4. El procedimiento especifico dentro de `03-operations/workflows/`

## Reglas

- Tratar todo dato juridico y personal como confidencial.
- No inventar hechos, fechas, montos, estados procesales, citas ni jurisprudencia.
- No confirmar vencimientos sin fuente oficial y fecha de verificacion.
- No enviar, presentar, firmar, publicar ni comunicar externamente sin aprobacion humana explicita.
- No modificar fuentes externas ni carpetas canonicas en una importacion sin `dry-run`, respaldo y aprobacion.
- Mantener separados staging, borradores y registros canonicos.
- No copiar datos entre clientes o asuntos.
- Si dos fuentes se contradicen, registrar el conflicto y solicitar validacion.

## Datos De Prueba

Usar exclusivamente fixtures sinteticos marcados como tales. Nunca convertir datos reales en ejemplos del repositorio.

