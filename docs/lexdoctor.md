# Integracion Con LexDoctor

## Alcance Seguro

La plantilla admite importaciones desde archivos CSV exportados de forma autorizada por el usuario. No presupone acceso a bases internas, automatizacion de interfaz ni una API no documentada.

## Flujo

1. Exportar una vista acotada desde LexDoctor.
2. Guardarla fuera de Git.
3. Copiar `config/lexdoctor-field-map.example.json` a un archivo local.
4. Ajustar los nombres de columnas.
5. Ejecutar una simulacion:

```powershell
python tools/import_lexdoctor_csv.py `
  --csv D:\Privado\lexdoctor.csv `
  --map config\lexdoctor-field-map.local.json `
  --out 00-inbox\integrations\lexdoctor-preview.json
```

6. Revisar los registros normalizados y los datos faltantes.
7. Incorporarlos al registro mediante un procedimiento aprobado.

## Limitaciones

- Los nombres de columnas varian entre instalaciones y exportaciones.
- Una fecha importada no se considera vencimiento confirmado sin fuente y validacion.
- El importador no escribe en LexDoctor ni crea carpetas.
- Los archivos exportados pueden contener datos sensibles y deben permanecer fuera de Git.

