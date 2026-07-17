# Integracion Con PJN Y Otros Portales

## Politica

Los portales judiciales son fuentes externas con posibles efectos juridicos. Este repositorio define un contrato de integracion, pero no distribuye credenciales, perfiles de navegador, tokens, cookies ni tecnicas de extraccion de sesiones.

## Diseño Recomendado

1. Obtener datos mediante un medio autorizado y documentado para la oficina.
2. Convertirlos al formato neutral de `integrations/pjn/pjn-event.example.json`.
3. Guardar los eventos reales en staging ignorado por Git.
4. Deduplicar por identificador externo y huella del evento.
5. Presentar diferencias para revision humana.
6. Actualizar el registro solamente despues de la aprobacion.

## Reglas

- Lectura por defecto; ninguna accion procesal automatica.
- No abrir documentos o notificaciones si la accion pudiera alterar su estado sin confirmacion expresa.
- No declarar vencimientos a partir de una inferencia del agente.
- Secretos y sesiones fuera del vault sincronizado.
- Logs sin documentos completos ni datos innecesarios.
- Adaptadores especificos se mantienen en repositorios privados separados cuando contienen particularidades de autenticacion u operacion.

`tools/import_pjn_event.py` valida un evento ya obtenido; no se conecta al portal.

