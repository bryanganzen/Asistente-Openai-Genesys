# Asistente-Openai-Genesys
Este desarrollo integra un Asistente OpenAI de prospección utilizando servicios de Genesys Cloud para integración

# Genesys Cloud Assistant Integration (Development Version)

## Descripción

Este proyecto integra un asistente desarrollado en Python con varios servicios, incluyendo Genesys Cloud, OpenAI y Google BigQuery. La aplicación está diseñada para manejar interacciones con usuarios, procesar datos y responder a solicitudes a través de una API RESTful construida con Flask.

### Características principales

- **Asistente con OpenAI**: Integra capacidades de conversación utilizando API Assistant de OpenAI para proporcionar respuestas automáticas y gestionar la interacción con el usuario.
- **Interacción con Genesys Cloud**: Utiliza la API de Genesys Cloud para gestionar datos de usuarios, colas e interacciones.
- **Consultas a BigQuery**: Permite realizar consultas a un proyecto de Google BigQuery para acceder a datos almacenados y procesarlos según sea necesario.
- **API RESTful con Flask**: Expone endpoints para recibir y procesar solicitudes, interactuando con los servicios mencionados para responder con la información requerida.

## Requisitos

- Python 3.x
- Librerías necesarias (ver `requirements.txt`):
  - `Flask`
  - `openai`
  - `requests`
  - `google-cloud-bigquery`
  - `PureCloudPlatformClientV2`
- Credenciales de acceso:
  - **OpenAI**: Clave API para acceder al Asistente.
  - **Genesys Cloud**: Token de acceso y configuración del entorno.
  - **Google BigQuery**: Archivo de credenciales JSON con permisos para acceder al proyecto.

## NOTA: Configura las credenciales necesarias:
- Coloca el archivo JSON con las credenciales de Google BigQuery en el directorio adecuado.

## Uso
**Inicia la aplicación Flask:**
- `python assistant_genesys_DEV.py`
- La aplicación estará disponible en `http://localhost:5000` para recibir solicitudes.
- Envía solicitudes a los endpoints definidos para interactuar con el asistente y los servicios integrados.

## Endpoints Disponibles
- **POST /chat:** Envía un mensaje al asistente y recibe una respuesta basada en la lógica definida.
- **GET /datos:** Realiza una consulta a BigQuery y devuelve los resultados.

## Estructura del Proyecto
- `assistant_genesys_DEV.py`: Script principal que contiene la lógica de la aplicación Flask y la integración con OpenAI, Genesys Cloud y BigQuery.
- `requirements.txt`: Archivo de dependencias necesarias para el proyecto.

## Contacto
Si tienes alguna pregunta o sugerencia, no dudes en ponerte en contacto.
- Bryan Ganzen
- 55 75 45 65 81
