# Extractor de cuestionarios

Aplicación web en React y FastAPI que extrae cuestionarios numerados de PDF, DOCX y XLSX. La extracción funciona con reglas locales y no requiere servicios de IA ni claves.

## Instalación local

Ejecuta los comandos desde la carpeta que contiene este README. Para las pruebas o la API necesitas Python 3.12. Para compilar la interfaz también necesitas Node.js 22 con npm. Si vas a desplegar directamente en Render, puedes pasar a **Despliegue**.

### Preparar Python

```sh
python -m venv .venv
```

Activa el entorno con el comando de tu terminal.

| Terminal | Comando |
| --- | --- |
| Git Bash en Windows | `source .venv/Scripts/activate` |
| PowerShell en Windows | `.venv\Scripts\Activate.ps1` |
| Linux o macOS | `source .venv/bin/activate` |

Luego instala las dependencias de Python en el entorno activo.

```sh
python -m pip install -r requirements-dev.txt
```

### Usar la aplicación en el navegador

Si todavía no existe `frontend/dist`, instala las dependencias de React y compila la interfaz. Si ya existe y no cambiaste el código de React, puedes pasar directamente al arranque del servidor.

```sh
npm --prefix frontend ci
npm --prefix frontend run build
```

Arranca el servidor y abre http://127.0.0.1:8000. Mantén la terminal abierta mientras usas la aplicación.

```sh
python -m uvicorn app.main:app
```

### Probar solo la API

Prepara Python y arranca Uvicorn con el comando anterior. Puedes omitir ambos comandos de npm. Abre http://127.0.0.1:8000/docs o ejecuta esta carga de ejemplo desde una segunda terminal.

```sh
curl -F "file=@examples/cuestionario.docx" http://127.0.0.1:8000/api/extract
```

### Ejecutar las pruebas automatizadas

Prepara Python y ejecuta el siguiente comando. Las pruebas funcionan sin compilar la interfaz ni iniciar Uvicorn.

```sh
python -m pytest -q
```

## Despliegue

Render instala las dependencias, compila la interfaz y arranca el servidor con el Dockerfile. Puedes omitir toda la instalación local si despliegas directamente en Render.

El Dockerfile compila React y sirve la aplicación y la API en el mismo origen. La única variable opcional es `PORT` (8000 por defecto). Los siguientes comandos son opcionales y sirven para probar Docker en tu computador.

```sh
docker build -t questionnaire .
docker run --rm -p 8000:8000 questionnaire
```

[Aplicación desplegada en Render](https://prueba-adipa.onrender.com/)

En Render, crea un Web Service desde el repositorio público y selecciona Docker como runtime. Usa el Dockerfile de la raíz y deja el comando de arranque predeterminado. Cuando el servicio esté disponible, sube uno de los ejemplos desde la interfaz para verificar el despliegue. [Guía de Render](https://render.com/docs/docker#building-from-a-dockerfile)

## Formatos y supuestos

- El título es la primera línea no vacía anterior al primer ítem. Cada enunciado comienza con un número seguido de punto o paréntesis y un espacio.
- Las alternativas ocupan líneas o celdas separadas. Usa `A) Texto` para letras y `0: Nunca` para valores numéricos.
- La respuesta correcta debe aparecer dentro del ítem como `Respuesta correcta: B`, `Correct answer: B` o `Risposta corretta: B`. Para emparejamiento, usa pares como `Perro=Mamífero, Rana=Anfibio`. Las alternativas de emparejamiento usan una flecha entre los términos. El JSON representa la clave de emparejamiento como un objeto.
- La clasificación se basa en las alternativas. Opcionalmente, agrega una etiqueta al comienzo del enunciado, por ejemplo `1. [escala_likert] Enunciado`. Sin alternativas, se asume desarrollo.
- La detección estadística del idioma usa el título y los enunciados. Devuelve `und` cuando el detector no identifica italiano, español o inglés. Un texto corto puede clasificarse incorrectamente.
- PDF requiere texto seleccionable. En XLSX se analiza la hoja activa de arriba hacia abajo y de izquierda a derecha. Las escalas globales, claves al final del documento, numeración automática de Word y maquetaciones complejas quedan fuera del formato admitido.
- Usa únicamente material inventado o de dominio público, sin datos personales. En `examples/` hay un cuestionario inventado de cinco ítems por idioma. Los archivos `cuestionario` están en español, `cuestionario-en` en inglés y `cuestionario-it` en italiano. Cada cuestionario está disponible en DOCX, PDF y XLSX, con un JSON de referencia compartido por los tres formatos. En los ejemplos, el ítem Likert mide frecuencia y su respuesta correcta es `null`. El ítem de desarrollo pide una respuesta breve e incluye una clave textual.
