import os
from flask import Flask, request, jsonify
from openai import OpenAI
import time
import json
import requests
import unicodedata
import math
import re
from datetime import datetime, timezone, timedelta
import PureCloudPlatformClientV2
from PureCloudPlatformClientV2.rest import ApiException
from pprint import pprint
from google.cloud import bigquery

app = Flask(__name__)

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"credenciales_json_de_BigQuery_aqui_dentro_del_proyecto"

bigquery_client = bigquery.Client()

client = OpenAI(api_key="api_key_openai_aqui",
                project="id_proyecto_openai_aqui")

assistant_id_all = "id_asistente_openai_aqui"

genesys_to_thread_table_id = "id_tabla_BigQuery_aqui"
ultima_respuesta_table_id = "id_tabla_BigQuery_aqui"
interaction_details_table_id = "id_tabla_BigQuery_aqui"

def create_new_thread():
    thread = client.beta.threads.create()
    thread_id = thread.id
    print(f"Nuevo thread creado: {thread_id}")
    return thread_id

def insert_into_bigquery(table_id, rows):
    rows_serializable = [{k: v.isoformat() if isinstance(v, datetime) else v for k, v in row.items()} for row in rows]
    errors = bigquery_client.insert_rows_json(table_id, rows_serializable)
    if errors:
        print(f"Errores al insertar en {table_id}:", errors)
    else:
        print(f"Datos insertados correctamente en {table_id}.")

def store_genesys_to_thread(genesys_id, thread_id):
    creation_timestamp = datetime.utcnow().replace(tzinfo=timezone.utc)
    rows = [{
        "genesys_id": genesys_id, 
        "thread_id": thread_id, 
        "creation_timestamp": creation_timestamp.isoformat()
        }]
    insert_into_bigquery(genesys_to_thread_table_id, rows)

def store_ultima_respuesta_por_genesys(genesys_id, response_time, thread_id, event_type, event_details=None):
    rows = [{
        "genesys_id": genesys_id,
        "response_time": response_time.isoformat(),
        "event_type": event_type,
        "thread_id": thread_id,
        "event_details": event_details
    }]
    insert_into_bigquery(ultima_respuesta_table_id, rows)

def store_interaction_details(interaction_data):
    rows = [interaction_data]
    insert_into_bigquery(interaction_details_table_id, rows)

def get_thread_id_from_bigquery(genesys_id):
    query = f"""
        SELECT thread_id 
        FROM {genesys_to_thread_table_id}
        WHERE genesys_id = @genesys_id
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("genesys_id", "STRING", genesys_id)
        ]
    )
    query_job = bigquery_client.query(query, job_config=job_config)
    results = query_job.result()

    for row in results:
        return row["thread_id"]
    
    return None

def get_most_recent_event(genesys_id):
    query = f"""
        SELECT event_type, response_time, thread_id 
        FROM {ultima_respuesta_table_id}
        WHERE genesys_id = @genesys_id
        ORDER BY response_time DESC
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("genesys_id", "STRING", genesys_id)
        ]
    )
    query_job = bigquery_client.query(query, job_config=job_config)
    results = query_job.result()

    for row in results:
        response_time_str = row["response_time"].isoformat() if isinstance(row["response_time"], datetime) else row["response_time"]
        return row["event_type"], datetime.fromisoformat(response_time_str), row["thread_id"]

    return None, None, None


def normalizar_cadena(cadena):
    cadena = cadena
    cadena_normalizada = ''.join(c for c in unicodedata.normalize('NFD', cadena) if unicodedata.category(c) != 'Mn').lower()
    return cadena_normalizada

def traer_programas_con_coincidencia(data, programa):
    resultados = []
    for programa_dict in data:
        nombre_programa = programa_dict.get('programa','')
        if programa in normalizar_cadena(nombre_programa):
            resultados.append({
                "valor1": programa_dict.get("valor1"),
                "valor2": programa_dict.get("valor2")
            })
    return resultados

def consultar_programa(programa):
    url_programa = 'api_para_consultar_programas'
    try:
        respuesta_programa = requests.get(url_programa)
        if respuesta_programa.status_code == 200:
            data = respuesta_programa.json()
            programa_normalizado = normalizar_cadena(programa)
            return traer_programas_con_coincidencia(data, programa_normalizado)
        else:
            return {"error": f"Error en la solicitud: {respuesta_programa.status_code}"}
    except Exception as e:
        return {"error": f"Ocurrió un error al realizar la solicitud: {e}"}

def ciclo(ciclo):
    url_ciclo = 'api_para_consultar_ciclos'
    respuesta_ciclo = requests.get(url_ciclo)
    if respuesta_ciclo.status_code == 200:
        catalogo = respuesta_ciclo.json()
        for programas in catalogo.values():
            for programa in programas:
                if programa.get("valor1") == int(ciclo):
                    ciclos = programa.get("ciclos", [])
                    return [ciclo["ciclo"] for ciclo in ciclos if "ciclo" in ciclo]
    return []

def beca(identificador, promedio_usuario):
    promedio_usuario = float(promedio_usuario)
    url_beca = 'api_para_consultar_beca'
    url_beca_completa = f"{url_beca}{identificador}"
    respuesta_beca = requests.get(url_beca_completa)
    if respuesta_beca.status_code == 200:
        respuesta_json = respuesta_beca.json()
        
        clave_programa = next(iter(respuesta_json["valor"]))
        programa = respuesta_json["valor"][clave_programa]
        
        if isinstance(programa["valor1"], list):
            duracion_minima = min(programa["valor1"], key=lambda x: x["valor2"])["valor2"]
        else:
            duracion_minima = programa["valor1"]["valor2"]
        
        precio_credito = programa["valor3"]["valor4"]["valor5"]
        monto_sin_beca = duracion_minima * precio_credito
        
        descuento_beca = 0
        for rango in programa["valor6"]:
            if rango["valor7"] <= promedio_usuario <= rango["valor8"]:
                descuento_beca = rango["valor9"]
                break
        
        monto_con_beca = monto_sin_beca * (1 - descuento_beca / 100)
        monto_ahorro = monto_sin_beca - monto_con_beca
        
        return {
            "valor10": duracion_minima,
            "valor11": math.ceil(monto_sin_beca),
            "valor12": descuento_beca,
            "valor13": math.ceil(monto_con_beca),
            "valor14": math.ceil(monto_ahorro),
            "valor15": programa["valor15"],
            "valor16": programa["valor16"]
        }
    else:
        return {'error': 'No se pudo obtener la información', 'status_code': respuesta_beca.status_code}

def fecha_actual():
    fecha_hora = datetime.now()
    return fecha_hora.strftime ("%A, %Y-%m-%d %H:%M:%S")

CAMPOS_REQUERIDOS_CITA = [
    "Valor1",
    "Valor2"
]

VALORES_DUMMY_CITA = {
    "valor1": ["valor1"],
    "valor2": ["valor2"]
}

CAMPUS_VALIDOS_CITA = {
    "valor1": "valor1.1",
    "valor2": "valor2.1"
}

CAMPUS_ENLINEA_CITA = ["valor1"]

def es_telefono_valido_cita(telefono):
    if telefono in VALORES_DUMMY_CITA["valor1"]:
        return False
    if telefono.isdigit() and len(telefono) == 10:
        consecutivos = all(int(telefono[i]) == int(telefono[i-1]) + 1 for i in range(1, len(telefono)))
        repetidos = all(telefono[i] == telefono[0] for i in range(1, len(telefono)))
        if consecutivos or repetidos:
            return False
    return True

def validar_campus_cita(campus):
    campus_normalizado = campus.upper()
    if campus_normalizado in CAMPUS_ENLINEA_CITA:
        return None, "\nLa cita no se puede programar: {}.".format(campus)
    if campus_normalizado in CAMPUS_VALIDOS_CITA:
        return CAMPUS_VALIDOS_CITA[campus_normalizado], None
    return campus, None

def validar_datos_cita(datos):
    errores = []
    for campo in CAMPOS_REQUERIDOS_CITA:
        if campo != "valor1":
            if campo not in datos or (isinstance(datos[campo], str) and not datos[campo].strip()):
                errores.append(f"\nFalta el campo requerido: {campo}")
    if "valor" in datos and datos["valor"].strip():
        datos["valor1"] = ""
    for campo_campus in ["valor1", "valor2"]:
        if campo_campus in datos:
            campus_corregido, error_campus = validar_campus_cita(datos[campo_campus])
            if error_campus:
                errores.append(error_campus)
            else:
                datos[campo_campus] = campus_corregido        
    for campo, valor_dummy in VALORES_DUMMY_CITA.items():
        if campo in datos:
            dato_normalizado = datos[campo].lower() if isinstance(datos[campo], str) else datos[campo]
            if isinstance(valor_dummy, list):
                if dato_normalizado in [dummy.lower() for dummy in valor_dummy] or not es_telefono_valido_cita(datos[campo]):
                    errores.append(f"\nEl campo {campo} contiene un valor inválido, solicitalo nuevamente: {datos[campo]}")
            elif dato_normalizado == valor_dummy.lower():
                errores.append(f"\nEl campo {campo} contiene un valor inválido, solicitalo nuevamente: {datos[campo]}")
    if "valor1" in datos:
        fecha_cita = datos["valor1"]
        try:
            datetime.strptime(fecha_cita, '%d/%m/%Y')
        except ValueError:
            try:
                fecha_corregida = datetime.strptime(fecha_cita, '%d-%m-%Y').strftime('%d/%m/%Y')
                datos["valor1"] = fecha_corregida
                print(f"Formato corregido a: {datos['valor1']}")
            except ValueError:
                try:
                    fecha_corregida = datetime.strptime(fecha_cita, '%Y/%m/%d').strftime('%d/%m/%Y')
                    datos["valor1"] = fecha_corregida
                    print(f"Formato corregido a: {datos['valor1']}")
                except ValueError:
                    try:
                        fecha_corregida = datetime.strptime(fecha_cita, '%Y-%m-%d').strftime('%d/%m/%Y')
                        datos["valor1"] = fecha_corregida
                        print(f"Formato corregido a: {datos['valor']}")
                    except ValueError:
                        errores.append(f"\nEl campo tiene un formato inválido: {fecha_cita}. Ajustalo antes de enviarlo.")
    return errores

url_cita = 'api_para_cita'

def enviar_registro_con_cita(url_cita, cita):
    errores = validar_datos_cita(cita)
    if errores:
        print("\nErrores de validación encontrados:")
        for error in errores:
            print(error)
        return {"error": "Errores de validación encontrados", "detalles": errores}
    try:
        print("\nEnviando los siguientes datos:", json.dumps(cita, indent=4))
        respuesta_cita = requests.post(url_cita, json=cita, headers={'Content-Type': 'application/json'})
        if respuesta_cita.status_code == 200:
            respuesta_json = respuesta_cita.json()
            print(json.dumps(respuesta_json, indent=4))
            response_s = respuesta_json.get("valor", {}).get("valor", {}).get("valor", [])
            if response_s and (response_s[0].get("valor") == "valor" or response_s[0].get("valor") == "success"):
                mensaje_adicional = (
                    f"Proporciona los detalles al usuario."
                )
                print("\n" + mensaje_adicional)
                return {
                    "valor": True,
                    "valor": True,
                    "valor": respuesta_json.get("valor", {}),
                    "valor": mensaje_adicional
                }
            else:
                return {"valor": False, "valor": False, "error": response_s[0].get("mensaje", "Error desconocido") if response_s else "Respuesta no encontrada"}
        else:
            print(f"\nError en la solicitud: {respuesta_cita.status_code}")
            print("\nDetalles del error:")
            print(respuesta_cita.text)
            return {"valor": False, "error": "Error en la respuesta"}
    except requests.exceptions.RequestException as e:
        print(f"\nOcurrió un error al realizar la solicitud: {e}")
        return {"error": f"Ocurrió un error al realizar la solicitud: {e}"}

CAMPOS_REQUERIDOS_REG = [
    "valor", 
    "valor"
]

VALORES_DUMMY_REGISTRO = {
    "valor": ["valor", "valor"],
    "valor": ["valor", "valor"]
}

CAMPUS_VALIDOS_REGISTRO = {
    "valor": "valor",
    "valor": "valor"
}

def es_telefono_valido_registro(telefono):
    if telefono in VALORES_DUMMY_REGISTRO["valor"]:
        return False
    if telefono.isdigit() and len(telefono) == 10:
        consecutivos = all(int(telefono[i]) == int(telefono[i-1]) + 1 for i in range(1, len(telefono)))
        repetidos = all(telefono[i] == telefono[0] for i in range(1, len(telefono)))
        if consecutivos or repetidos:
            return False
    return True

def validar_campus_registro(campus):
    campus_normalizado = campus.upper()
    if campus_normalizado in CAMPUS_VALIDOS_REGISTRO:
        return CAMPUS_VALIDOS_REGISTRO[campus_normalizado], None
    return campus, None

def validar_datos_registro(datos):
    errores = []
    for campo in CAMPOS_REQUERIDOS_REG:
        if campo != "valor":
            if campo not in datos or (isinstance(datos[campo], str) and not datos[campo].strip()):
                errores.append(f"\nFalta el campo requerido: {campo}")
    if "valor" in datos and datos["valor"].strip():
        print(f"\nEl campo valor tenía datos, se formatea para estar vacío.")
        datos["valor"] = ""
    for campo_campus in ["valor"]:
        if campo_campus in datos:
            campus_corregido, error_campus = validar_campus_registro(datos[campo_campus])
            if error_campus:
                errores.append(error_campus)
            else:
                datos[campo_campus] = campus_corregido
    for campo, valor_dummy in VALORES_DUMMY_REGISTRO.items():
        if campo in datos:
            dato_normalizado = datos[campo].lower() if isinstance(datos[campo], str) else datos[campo]
            if isinstance(valor_dummy, list):
                if dato_normalizado in [dummy.lower() for dummy in valor_dummy] or not es_telefono_valido_registro(datos[campo]):
                    errores.append(f"\nEl campo {campo} contiene un valor inválido, , solicitalo nuevamente: {datos[campo]}")
            elif dato_normalizado == valor_dummy.lower():
                errores.append(f"\nEl campo {campo} contiene un valor inválido, , solicitalo nuevamente: {datos[campo]}")
    return errores

url_registro = 'api_para_registro'

def enviar_registro_sin_cita(url_registro, registro):
    errores = validar_datos_registro(registro)
    if errores:
        print("\nErrores de validación encontrados: ")
        for error in errores:
            print(error)
        return {"error": "Errores de validación encontrados", "detalles": errores}
    try:
        print("\nEnviando los siguientes datos:", json.dumps(registro, indent=4))
        respuesta_registro = requests.post(url_registro, json=registro, headers={'Content-Type': 'application/json'})
        if respuesta_registro.status_code == 200:
            respuesta_json = respuesta_registro.json()
            print(json.dumps(respuesta_json, indent=4))
            response_s = respuesta_json.get("valor", {}).get("scrvaloribe", {}).get("valor", [])
            if response_s and (response_s[0].get("valor") == "valor" or response_s[0].get("valor") == "success"):
                mensaje_adicional = (
                    f"Proporciona los detalles al usuario."
                )
                print("\n" + mensaje_adicional)
                return {
                    "valor": True,
                    "valor": True,
                    "valor": respuesta_json.get("valor", {}),
                    "valor": mensaje_adicional
                }
            else:
                return {"valor": False, "valor": False, "error": response_s[0].get("mensaje", "Error desconocido") if response_s else "Respuesta no encontrada"}
        else:
            print(f"\nError en la solicitud: {respuesta_registro.status_code}")
            print("\nDetalles del error:")
            print(respuesta_registro.text)
    except requests.exceptions.RequestException as e:
        print(f"\nOcurrió un error al realizar la solicitud: {e}")
        return {"error": f"Ocurrió un error al realizar la solicitud: {e}"}

CAMPOS_REQUERIDOS_MICROREGISTRO = [
    "valor", 
    "valor"
    ]

VALORES_DUMMY_MICROREGISTRO = {
    "valor": ["valor", "valor"],
    "valor": ["valor", "valor"]
}

CAMPUS_VALIDOS_MICROREGISTRO = {
    "valor": "valor",
    "valor": "valor"
}

def es_telefono_valido_microregistro(telefono):
    if telefono in VALORES_DUMMY_MICROREGISTRO["valor"]:
        return False
    if telefono.isdigit() and len(telefono) == 10:
        consecutivos = all(int(telefono[i]) == int(telefono[i-1]) + 1 for i in range(1, len(telefono)))
        repetidos = all(telefono[i] == telefono[0] for i in range(1, len(telefono)))
        if consecutivos or repetidos:
            return False
    return True

def validar_campus_microregistro(campus):
    campus_normalizado = campus.upper()
    if campus_normalizado in CAMPUS_VALIDOS_MICROREGISTRO:
        return CAMPUS_VALIDOS_MICROREGISTRO[campus_normalizado], None
    return campus, None

def validar_datos_microregistro(datos):
    errores = []
    for campo in CAMPOS_REQUERIDOS_MICROREGISTRO:
        if campo not in ["valor", "valor"]:
            if campo not in datos or (isinstance(datos[campo], str) and not datos[campo].strip()):
                errores.append(f"\nFalta el campo requerido o está vacío: {campo}")
    for campo_excluir in ["valor", "valor"]:
        if campo_excluir in datos and datos[campo_excluir].strip():
            print(f"\nEl campo {campo_excluir} tenía datos, se formatea para estar vacío.")
            datos[campo_excluir] = ""
    for campo_campus in ["valor"]:
        if campo_campus in datos:
            campus_corregido, error_campus = validar_campus_microregistro(datos[campo_campus])
            if error_campus:
                errores.append(error_campus)
            else:
                datos[campo_campus] = campus_corregido
    for campo, valor_dummy in VALORES_DUMMY_MICROREGISTRO.items():
        if campo in datos:
            dato_normalizado = datos[campo].lower() if isinstance(datos[campo], str) else datos[campo]
            if isinstance(valor_dummy, list):
                if dato_normalizado in [dummy.lower() for dummy in valor_dummy] or not es_telefono_valido_microregistro(datos[campo]):
                    errores.append(f"\nEl campo {campo} contiene un valor inválido, solicitalo al nuevamente: {datos[campo]}")
            elif dato_normalizado == valor_dummy.lower():
                errores.append(f"\nEl campo {campo} contiene un valor inválido, solicitalo nuevamente: {datos[campo]}")
    if "valor" in datos:
        fecha_cita = datos["valor"]
        try:
            datetime.strptime(fecha_cita, '%d/%m/%Y')
        except ValueError:
            try:
                fecha_corregida = datetime.strptime(fecha_cita, '%d-%m-%Y').strftime('%d/%m/%Y')
                datos["valor"] = fecha_corregida
                print(f"Formato corregido a: {datos['valor']}")
            except ValueError:
                try:
                    fecha_corregida = datetime.strptime(fecha_cita, '%Y/%m/%d').strftime('%d/%m/%Y')
                    datos["valor"] = fecha_corregida
                    print(f"Formato corregido a: {datos['valor']}")
                except ValueError:
                    try:
                        fecha_corregida = datetime.strptime(fecha_cita, '%Y-%m-%d').strftime('%d/%m/%Y')
                        datos["valor"] = fecha_corregida
                        print(f"Formato corregido a: {datos['valor']}")
                    except ValueError:
                        errores.append(f"\nEl campo tiene un formato inválido: {fecha_cita}. Ajustalo antes de enviarlo.")
    return errores

url_microregistro = 'api_micro'

def enviar_microregistro_con_cita(url_microregistro, micro):
    errores = validar_datos_microregistro(micro)
    if errores:
        print("\nErrores de validación encontrados:")
        for error in errores:
            print(error)
        return {"error": "Errores de validación encontrados", "detalles": errores}
    try:
        print("\nEnviando los siguientes datos:", json.dumps(micro, indent=4))
        respuesta_s = requests.post(url_microregistro, json=micro, headers={'Content-Type': 'application/json'})
        if respuesta_s.status_code == 200:
            respuesta_json = respuesta_s.json()
            print(json.dumps(respuesta_json, indent=4))
            if respuesta_json.get("valor") == 1:
                mensaje_adicional = (
                    f"Proporciona los detalles de la cita al usuario"
                )
                print("\n" + mensaje_adicional)
                return {
                    "valor": True,
                    "valor": True,
                    "valor": respuesta_json,
                    "valor": mensaje_adicional
                }
            else:
                return {"valor": False, "valor": False, "error": respuesta_json.get("message", "Error desconocido")}
        else:
            print(f"\nError en la solicitud: {respuesta_s.status_code}")
            print("\nDetalles del error:")
            print(respuesta_s.text)
            return {"valor": False, "error": "Error en la respuesta"}
    except requests.exceptions.RequestException as e:
        print(f"\nOcurrió un error al realizar la solicitud: {e}")
        return {"error": f"Ocurrió un error al realizar la solicitud: {e}"}

def transfer(departamento):
    resultado = {
        "status": "Transferencia realizada",
        "departamento": departamento
    }
    return resultado

def limpiar_referencias(texto):
    patron_referencias = r'【[^】]*\.pdf】|【[^\】]*†[^\】]*】'
    texto_limpio = re.sub(patron_referencias, '', texto)
    return texto_limpio

def obtener_token():
    url = "token_genesys_cloud"
    try:
        respuesta = requests.get(url)
        if respuesta.status_code == 200:
            token = respuesta.json().get('token')
            return token
        else:
            print(f"Error al obtener el token: {respuesta.status_code}")
            return None
    except Exception as e:
        print(f"Error al realizar la solicitud para obtener el token: {e}")
        return None
    
def obtener_datos_usuario(conversation_id, token):
    PureCloudPlatformClientV2.configuration.host = "host_region_genesys_cloud"
    PureCloudPlatformClientV2.configuration.access_token = token
    api_instance = PureCloudPlatformClientV2.ConversationsApi()

    try:
        api_response = api_instance.get_conversations_message(conversation_id)

        for participant in api_response.participants:
            if participant.purpose == "valor":
                nick_name = participant.from_address.name if hasattr(participant.from_address, 'valor') else 'Desconocido'
                tel_wa = participant.from_address.address_normalized if hasattr(participant.from_address, 'valor') else 'Desconocido'
                canal = participant.attributes.get('valor', 'valor') if hasattr(participant, 'valor') else 'Desconocido'

                return nick_name, tel_wa, canal

        return None, None, None
    except ApiException as e:
        print(f"Error al obtener los datos del usuario: {e}")
        return None, None, None

def obtener_texto_mensajes(conversation_id, message_id, token):
    PureCloudPlatformClientV2.configuration.host = "host_region_genesys_cloud"
    PureCloudPlatformClientV2.configuration.access_token = token
    api_instance = PureCloudPlatformClientV2.ConversationsApi()
    
    try:
        api_response = api_instance.get_conversations_message_message(conversation_id, message_id, use_normalized_message=False)

        return api_response.text_body if hasattr(api_response, 'valor') else None
    except ApiException as e:
        print(f"Error al obtener el mensaje {message_id}: {e}")
        return None

def obtener_ids_mensajes_usuario(conversation_id, token, start_datetime):
    PureCloudPlatformClientV2.configuration.host = "host_region_genesys_cloud"
    PureCloudPlatformClientV2.configuration.access_token = token
    api_instance = PureCloudPlatformClientV2.ConversationsApi()

    try:
        api_response = api_instance.get_conversations_message(conversation_id)
        mensajes_usuario = []
        ultimo_end_time = None

        for participant in api_response.participants:
            if participant.purpose == "valor" and participant.state == "valor":
                if hasattr(participant, 'valor') and participant.disconnect_type == "valor":
                    end_time = participant.end_time.replace(tzinfo=timezone.utc)
                    if not ultimo_end_time or end_time > ultimo_end_time:
                        ultimo_end_time = end_time
                        store_ultima_respuesta_por_genesys(conversation_id, end_time, "valor", "Agente desconectado")
        if ultimo_end_time:
            start_datetime = max(start_datetime, ultimo_end_time)
        
        start_datetime -= timedelta(seconds=1)

        for participant in api_response.participants:
            if participant.purpose == "valor":
                for message in participant.messages:
                    if hasattr(message, 'valor') and hasattr(message, 'valor'):
                        message_time = message.message_time.replace(tzinfo=timezone.utc)
                        print(f"Comparando valor {message_time} con valor {start_datetime}")
                        if message_time >= start_datetime:
                            text_body = obtener_texto_mensajes(conversation_id, message.message_id, token)
                            if text_body:
                                mensajes_usuario.append({
                                    'valor': message.message_id,
                                    'valor': message_time,
                                    'valor': text_body
                                    })

        mensajes_usuario.sort(key=lambda x: x['valor'])

        return mensajes_usuario
    except ApiException as e:
        print(f"Error al obtener los mensajes de la conversación: {e}")
        return []
    
@app.route('/valor', methods=['POST'])
def send_message():
    data = request.json
    genesys_id = data.get('valor')
    start = data.get('valor')

    if not genesys_id:
        return jsonify({"error": "valor es requerido"}), 400
    
    print("Esperando 10 segundos para dar respuesta...")
    time.sleep(10)

    event_type, start_datetime, thread_id = get_most_recent_event(genesys_id)
    print(f"Evento más reciente: {event_type}, valor datetime: {start_datetime}, valor ID: {thread_id}")

    if not thread_id:
        thread_id = get_thread_id_from_bigquery(genesys_id)
        if thread_id:
            print(f"valor existente recuperado: {thread_id}")
        else:
            thread_id = create_new_thread()
            store_genesys_to_thread(genesys_id, thread_id)
            print(f"Nuevo valor creado y almacenado: {thread_id}")

    if not start_datetime:
        if start:
            try:
                start_datetime = datetime.fromisoformat(start.replace("Z", "+00:00"))
                if start_datetime.tzinfo is None:
                    start_datetime = start_datetime.replace(tzinfo=timezone.utc)
            except ValueError:
                return jsonify({"error": "El formato no es válido"}), 400
        else:
            start_datetime = datetime.utcnow().replace(tzinfo=timezone.utc)
    
    print(f"valor final: {start_datetime}")

    token = obtener_token()
    if not token:
        return jsonify({"error": "No se pudo obtener el token de acceso"}), 500

    interaction_data = {
        "valor": genesys_id,
        "valor": start_datetime
    }

    try:
        nick_name, tel_wa, canal = obtener_datos_usuario(genesys_id, token)
        interaction_data["valor"] = nick_name
        interaction_data["valor"] = tel_wa
        interaction_data["valor"] = canal
        print(f"Datos del usuario obtenidos: valor={nick_name}, valor={tel_wa}, valor={canal}")

        mensajes_usuario = obtener_ids_mensajes_usuario(genesys_id, token, start_datetime)
        print(f"Mensajes del usuario obtenidos: {mensajes_usuario}")

        if not mensajes_usuario:
            print("No hay más mensajes.")
            return jsonify({
                "valor": thread_id,
                "valor": genesys_id,
                "valor": "Aún no hay más mensajes después de la última respuesta del asistente."
            })

        mensaje_concatenado = " ".join(mensaje['text_body'] for mensaje in mensajes_usuario)
        interaction_data["mensaje_usuario_concatenado"] = mensaje_concatenado

        if not mensaje_concatenado:
            print("El mensaje concatenado está vacío.")
            return jsonify({
                "valor": thread_id,
                "valor": genesys_id,
                "valor": "El mensaje concatenado está vacío."
            })

        departamento = None

        interaccion_start_time = time.time()

        print(f"Enviando mensaje al valor {thread_id}: {mensaje_concatenado}")
        message = client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=mensaje_concatenado
        )

        print(f"\nLa traza es: {message}")

        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread_id,
            assistant_id=assistant_id_all
        )
        print("\nCargando respuesta...", end="")

        while True:
            run = client.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run.id
            )

            if run.status == 'completed':
                print("\nRespuesta completada.")
                interaccion_end_time = time.time()
                interaccion_duration = interaccion_end_time - interaccion_start_time
                respuesta_datetime = datetime.utcnow().replace(tzinfo=timezone.utc)

                messages = client.beta.threads.messages.list(
                    thread_id=thread_id
                )
                texto_limpio = limpiar_referencias(messages.data[0].content[0].text.value)
                interaction_data["respuesta_asistente"] = texto_limpio

                store_ultima_respuesta_por_genesys(genesys_id, respuesta_datetime, thread_id, "assistant_response", mensaje_concatenado)

                interaction_data["valor"] = respuesta_datetime
                interaction_data["valor"] = "assistant_response"

                store_interaction_details(interaction_data)
                break

            elif run.status == 'requires_action':
                print(f"\nEl estado del run es: {run.status}")
                tool_outputs = []

                for tool_call in run.required_action.submit_tool_outputs.tool_calls:
                    func_name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments)
                    print(f"\ntool: {tool_call.function.arguments}")

                    if func_name == "valor":
                        output = consultar_programa(arguments["valor"])
                        if isinstance(output, list) and output:
                            interaction_data["valor"] = output[0].get("valor")
                    elif func_name == "valor":
                        output = ciclo(arguments["valor"])
                        if output:
                            interaction_data["valor"] = output[0]
                    elif func_name == "valor":
                        output = beca(arguments["valor"], arguments["valor"])
                        interaction_data["valor"] = arguments["valor"]
                        if isinstance(output, dict):
                            interaction_data["valor"] = output.get("valor")
                    elif func_name == "valor":
                        output = fecha_actual()
                    elif func_name == "valor":
                        output = enviar_microregistro_con_cita(url_microregistro, arguments)
                        interaction_data["valor"] = json.dumps(arguments)
                        if not output.get("valor"):
                            interaction_data["valor"] = output.get("error", "Error desconocido")
                        interaction_data["valor"] = f"{arguments.get('valor')} {arguments.get('valor')} {arguments.get('valor')}"
                        interaction_data["valor"] = str(arguments.get("valor"))
                        interaction_data["valor"] = arguments.get("valor")
                        
                        fecha_cita_original = arguments.get("valor", "")
                        if fecha_cita_original:
                            try:
                                fecha_cita_formateada = datetime.strptime(fecha_cita_original, "%d/%m/%Y").strftime("%Y-%m-%d 00:00:00")
                            except ValueError:
                                fecha_cita_formateada = None
                                interaction_data["valor"] = "Formato inválido"
                        else:
                            fecha_cita_formateada = None
                            interaction_data["valor"] = "valor no proporcionado"

                        interaction_data["valor"] = fecha_cita_formateada
                        interaction_data["valor"] = arguments.get("valor")
                    elif func_name == "valor":
                        output = enviar_registro_con_cita(url_cita, arguments)
                        interaction_data["valor"] = json.dumps(arguments)
                        if not output.get("valor"):
                            interaction_data["valor"] = output.get("error", "Error desconocido")
                        interaction_data["valor"] = f"{arguments.get('valor')} {arguments.get('valor')} {arguments.get('valor')}"
                        interaction_data["valor"] = str(arguments.get("valor"))
                        interaction_data["valor"] = arguments.get("valor")
                        
                        fecha_cita_original = arguments.get("valor", "")
                        if fecha_cita_original:
                            try:
                                fecha_cita_formateada = datetime.strptime(fecha_cita_original, "%d/%m/%Y").strftime("%Y-%m-%d 00:00:00")
                            except ValueError:
                                fecha_cita_formateada = None
                                interaction_data["valor"] = "Formato inválido"
                        else:
                            fecha_cita_formateada = None
                            interaction_data["valor"] = "valor no proporcionado"

                        interaction_data["valor"] = fecha_cita_formateada
                    elif func_name == "valor":
                        output = enviar_registro_sin_cita(url_registro, arguments)
                        interaction_data["valor"] = json.dumps(arguments)
                        if not output.get("valor"):
                            interaction_data["valor"] = output.get("error", "Error desconocido")
                        interaction_data["valor"] = f"{arguments.get('valor')} {arguments.get('valor')} {arguments.get('valor')}"
                        interaction_data["valor"] = str(arguments.get("valor"))
                        interaction_data["valor"] = arguments.get("valor")
                    elif func_name == "valor":
                        output = transfer(arguments.get("valor", "valor1"))
                        departamento = output["valor"]
                        interaction_data["valor"] = True
                        interaction_data["valor"] = departamento
                    else:
                        output = None

                    output_str = json.dumps(output) if isinstance(output, (dict, list)) else str(output)
                    tool_outputs.append({
                        "tool_call_id": tool_call.id,
                        "output": output_str
                    })

                client.beta.threads.runs.submit_tool_outputs(
                    thread_id=thread_id,
                    run_id=run.id,
                    tool_outputs=tool_outputs
                )
                print("\nDatos de salida de la función en ejecución en turno: ", tool_outputs)
                print("\nEstos son los datos que estoy recibiendo del API en turno: ", tool_outputs)

    except Exception as e:
        interaction_data["valor"] = str(e)
        interaction_data["valor"] = True
        store_interaction_details(interaction_data)
        return jsonify({"error": "Se produjo un error en el servicio de OpenAI"}), 500

    response = {
        "valor": thread_id,
        "valor": genesys_id,
        "valor": interaction_data["valor"],
        "valor": interaction_data["valor"].strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
        "valor": interaccion_duration,
    }

    if departamento:
        response["valor"] = departamento

    print("Respuesta final del API:")
    pprint(response)

    return jsonify(response)


if __name__ == '__main__':
    app.run(debug=True)