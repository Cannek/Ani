# Aniriame: servidor y base de datos (versión 0.2)

## Qué hay en esta carpeta
- `aniriame.db`: la base de datos (léxico del CEEES y tablas vacías para documentos y revisiones).
- `main.py`: el servidor.
- `aniriame_db.py`: las funciones que hablan con la base (buscar, guardar, revisar, indicadores).
- `motor.py`: el motor de traducción. **Hoy es un marcador de prueba, no traduce a rarámuri.**
- `build_db.py`: reconstruye la base desde el CSV del CEEES (solo si hace falta empezar de cero).
- `importar_pares.py` y `plantilla_pares.csv`: para cargar documentos ya traducidos.

## Para encenderlo (una sola vez la instalación)
1. Abre la terminal dentro de esta carpeta.
2. Instala lo necesario: `pip install -r requirements.txt`
3. Enciende el servidor: `uvicorn main:app --reload`
4. Abre en el navegador: `http://127.0.0.1:8000/docs`. Ahí puedes probar cada ruta con botones, sin escribir código.

## Entrenar la base con pares ya establecidos
En la pestaña Entrenar puedes cargar pares de párrafos (español y rarámuri) ya traducidos y revisados, uno por uno o con un CSV (columnas `texto_es` y `texto_rar`, y opcionalmente `documento` y `area`; ver `plantilla_pares.csv`). Antes de guardar, la página muestra una ventana de confirmación con el resumen.
- Nivel de confianza en estrellas: 5 = referencia validada (se usa como ejemplo para traducir); 3 o 4 = se guarda como revisado, pero no se usa como ejemplo; 1 o 2 = queda pendiente.
- Repetidos: se omiten.
- Conflictos: si el español ya tiene otra traducción validada, el par nuevo entra como pendiente, para que una persona decida y no se reemplace en silencio una referencia.
- Cada carga queda firmada con el nombre que escribas arriba en la página.

## Plantilla de Excel para cargas grandes
En Entrenar hay dos descargas: "Descargar plantilla Excel" (dos columnas con nombres fijos, texto_es y texto_rar, un par por fila, con la fila 1 protegida y una hoja de instrucciones) y "Ejemplo CSV". El Excel lleno se sube con "Cargar Excel o CSV": los pares aparecen en la lista para revisarlos, se elige el nivel de confianza y se confirma antes de guardar. La plantilla no lleva contraseña: la protección solo evita cambios accidentales. Las filas de ejemplo (que empiezan con "EJEMPLO") se ignoran al cargar.

## Archivos PDF y Word
En la pestaña Traducir, "Elegir archivo" acepta PDF, Word (.docx) y .txt. El texto aparece en el cuadro para que lo revises y lo edites antes de traducir. Los PDF escaneados (solo imagen) todavía no se pueden leer, y los Word antiguos (.doc) deben guardarse como .docx. Los textos largos se traducen en tandas de 5 párrafos con un contador de avance, y la página pide confirmación si pasan de 30 párrafos.

## Conectar el motor de traducción (API de Claude)
1. Instala lo nuevo: `python -m pip install -r requirements.txt`
2. Crea una clave de API en la Consola de Claude y carga un saldo pequeño. Guárdala bien: no la pegues en archivos, chats ni repositorios.
3. Opción recomendada: un archivo `.env`. En VS Code, clic derecho en la carpeta, Nuevo archivo, y ponle exactamente `.env` (no `.env.txt`). Pega ahí el contenido de `env.ejemplo` con tu clave. Después apaga el servidor (Ctrl+C) y enciéndelo de nuevo: los cambios al `.env` no se recargan solos.
   - Nunca compartas ni subas ese archivo. Si algún día usan Git, agrega `.env` y `aniriame.db` al `.gitignore`.
   - La clave solo debe vivir en el equipo que hace de servidor, no en las laptops que se prestan.

   Alternativa sin archivo, en la misma terminal donde vas a encender el servidor:
   - PowerShell (el prompt empieza con `PS`): `$env:ANTHROPIC_API_KEY="tu-clave"`
   - Símbolo del sistema (cmd): `set ANTHROPIC_API_KEY=tu-clave`
4. Enciende el servidor. La página debe decir "Conectado · motor: Claude (...)".
5. Para probar otro modelo: `$env:ANIRIAME_MODELO="claude-haiku-5-5"` (o `claude-opus-5-5`) antes de encender.

Los textos que traduzcas salen a un servicio externo. Para el piloto, usa solo textos de prueba o públicos.

## Si algo falla
- **"no such table"** o un aviso de que la base está vacía: el archivo `aniriame.db` de tu carpeta está vacío o no es el correcto. Apaga el servidor (Ctrl+C), borra ese archivo y copia el `aniriame.db` original (pesa unos 650 KB). Si no lo tienes, reconstrúyelo con el CSV del CEEES en la misma carpeta: `python build_db.py raramuri-base-lexicografica-completa.csv aniriame.db`
- **"No encuentro la base de datos"**: el servidor se encendió desde otra carpeta. El mensaje dice dónde la buscó.

## Rutas
- `GET /buscar?q=abuela`: busca en el léxico, de español a rarámuri.
- `POST /traducir`: recibe un texto, lo divide en párrafos y devuelve una referencia validada si ya existe, o un borrador por revisar.
- `GET /pendientes`: borradores que esperan a la persona evaluadora.
- `POST /revisar`: estrellas (0 a 5) y corrección. Con 5 estrellas, o con una corrección, el resultado pasa a ser referencia validada.
- `POST /pares`: agrega una frase o un párrafo con su traducción.
- `GET /indicadores`: avance y crecimiento.

## Protección de acceso
Por defecto no pide clave. Para pedirla en las rutas que escriben, define antes de encender el servidor:
- Mac o Linux: `export ANIRIAME_TOKEN="una-clave-larga"`
- Windows: `set ANIRIAME_TOKEN=una-clave-larga`

Después, esas rutas piden el encabezado `X-Token` con esa clave.

## Cargar documentos ya traducidos
Llena `plantilla_pares.csv` (una fila por párrafo) y corre:
`python importar_pares.py documentos.csv --validado-por "Nombre" --estado validado`

## Cómo se calculan los indicadores
- `pct_aceptables`: de los borradores del sistema ya revisados, el porcentaje que quedó sin corrección con 4 o 5 estrellas, o con una corrección menor (el texto corregido se parece al original en al menos 90%).
- `crecimiento_semanal`: referencias nuevas por semana que salen del uso (revisiones y correcciones). No cuenta el corpus histórico importado, para que no infle el crecimiento.

## Pendiente
- Conectar un motor de traducción real en `motor.py`.
- Conectar la página al servidor.
- Pantalla de revisión para la persona evaluadora.
- Pasar los identificadores a únicos por equipo, antes de sincronizar varios equipos.
