# Seguridad Y Privacidad

## Regla Central

El repositorio de plantilla no debe contener datos de clientes, expedientes reales, credenciales, tokens, cookies, perfiles de navegador, documentos juridicos reales, modelos propios de un estudio ni resultados de consultas a sistemas externos.

## Datos Vivos

Las carpetas operativas sensibles estan ignoradas por Git. Si el estudio necesita versionado o respaldo, debe usar una solucion privada aprobada, cifrada y con control de acceso; no debe quitar las exclusiones sin una evaluacion formal.

## Integraciones

- Guardar secretos fuera del directorio sincronizado y fuera del repositorio.
- Usar variables de entorno o un gestor de secretos.
- No persistir tokens de sesion, cookies o perfiles de navegador dentro del vault.
- Ejecutar importaciones en `dry-run` y staging antes de aplicar cambios.
- No asumir que una operacion de lectura carece de efectos procesales: verificarlo con la fuente oficial y el responsable del estudio.

## Reportes

No abrir issues publicos con informacion real. En repositorios privados, reducir igualmente los datos al minimo indispensable y revocar cualquier credencial expuesta.

