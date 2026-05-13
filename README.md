# TDA Salud CDMX

Proyecto de análisis topológico de datos económicos geolocalizados del sector salud en Ciudad de México, usando datos DENUE 2025 y herramientas de persistencia homológica.

## Objetivo

Identificar patrones de conectividad, concentración y posibles huecos de cobertura en servicios de salud de la Ciudad de México mediante complejos de Vietoris-Rips y homología persistente.

## Datos

Se utilizan datos del DENUE 2025 para Ciudad de México.

Cada integrante debe descargar el archivo `denue_09_csv.zip` y colocarlo en:

```text
data/raw/denue_09_csv.zip

## Descarga de datos

Para descargar el archivo DENUE de CDMX, ejecutar desde la raíz del repositorio:

```bash
mkdir -p data/raw

curl -L "https://cfcetlsadls.blob.core.windows.net/raw/inegi/denue_por_estado/ciudad_de_mexico_zip/denue_09_csv.zip?sv=2025-07-05&spr=https&st=2026-04-24T19%3A24%3A46Z&se=2026-06-09T19%3A24%3A00Z&sr=b&sp=r&sig=%2F5%2BqqFCki1Y%2Bdl3Y21slq3HOd7Ek5cDjh849JlR37Dc%3D" -o data/raw/denue_09_csv.zip