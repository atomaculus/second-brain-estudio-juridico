# Arquitectura

## Capas

1. **Fuentes externas:** carpetas, LexDoctor, portales judiciales, calendario o correo.
2. **Staging:** propuestas de importacion que todavia no son canonicas.
3. **Registro operativo:** clientes, asuntos y mapa de carpetas canonicas.
4. **Conocimiento:** criterios autorizados y material reusable sin datos innecesarios.
5. **Salidas:** borradores sujetos a revision humana.

```text
fuente externa -> adaptador -> staging -> validacion humana -> registro canonico
                                      \-> conflicto / dato faltante
```

## Identidad De Un Asunto

Cada asunto posee un `matterId` interno estable. Los numeros de expediente, IDs de LexDoctor y nombres de carpeta son identificadores externos o alias; ninguno debe reemplazar al identificador interno.

## Contrato De Adaptadores

Un adaptador debe producir registros normalizados sin modificar la fuente:

- `sourceSystem`
- `externalId`
- `caseNumber`
- `caption`
- `client`
- `jurisdiction`
- `court`
- `status`
- `nextDeadline`
- `sourceUpdatedAt`
- `sourceReference`

Los resultados se revisan antes de incorporarse al registro.

## Portabilidad

Las rutas, nombres de columnas y sistemas externos viven en configuracion local. Los scripts no deben contener nombres de clientes, rutas de una oficina, credenciales ni IDs reales.

