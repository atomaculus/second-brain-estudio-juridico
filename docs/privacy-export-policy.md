# Politica Para Distribuir La Plantilla

## Permitido

- Estructura de directorios.
- Esquemas y contratos abstractos.
- Plantillas vacias.
- Datos sinteticos identificados como tales.
- Procedimientos generales de seguridad, auditoria y aprobacion.
- Herramientas que operan sobre configuracion local.

## Prohibido

- Nombres, documentos, expedientes, IDs, rutas o resultados reales.
- Modelos juridicos y criterios propios de una oficina sin autorizacion expresa.
- Registros, handoffs, historiales, reportes o logs de produccion.
- Tokens, cookies, perfiles de navegador y secretos.
- Detalles de autenticacion o automatizacion derivados de sesiones reales.

## Regla De Implementacion Limpia

Las funciones portables se describen como contratos y se implementan con fixtures sinteticos. No se copian archivos operativos para luego “anonimizarlos”, porque pueden conservar metadatos o detalles identificables.

