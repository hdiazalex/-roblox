# Propuesta: aplicación de crucigramas crípticos (ES/EN, web + móvil)

> Estado: **borrador para aprobación**. No hay código todavía.
> Fecha: 14-10-2026. Los precios y licencias citados se comprobaron en esa fecha.
> Cada licencia se volverá a comprobar en su fichero `LICENSE` original al
> incorporar el recurso (Fase 2); no soy abogado y algunas fuentes consultadas
> son secundarias (se indica cuándo).

---

## 0. Resumen de recomendaciones

| # | Decisión | Recomendación |
|---|---|---|
| 1a | Rellenar la cuadrícula | Plantillas simétricas de estilo británico (con casillas no cruzadas) + relleno por búsqueda con restricciones, **solo con palabras para las que ya sabemos escribir pista** |
| 1b | Escribir las pistas | **Mixto**: las reglas construyen y verifican el juego de palabras; la IA solo redacta la frase superficial; un verificador determinista y un "solucionador a ciegas" filtran |
| 1c | Cuándo generar | **Por adelantado, en lote**, revisados por métricas y servidos como ficheros estáticos |
| 1d | Recursos léxicos | EN: SCOWL, Open English WordNet, CMUdict, wordfreq. ES: diccionario Hunspell RLA-ES, tesauro RLA-ES, WordNet español (MCR). Ambos: lista LDNOOBW + listas propias |
| 1e | Tamaño inicial | 7×7 para desarrollo, **9×9 en la versión 1**, 13×13 y 15×15 después |
| 2 | Plataforma | **PWA** (React + TypeScript + Vite) con la lógica en paquetes TypeScript independientes; **Capacitor** más adelante si se quieren tiendas |
| — | Backend/cuentas | Ficheros estáticos en CDN + **Supabase** (región UE) solo para cuentas y progreso; acceso por **código de un solo uso por email** |
| 3 | Alcance v1 | Resolver 9×9 crípticos en ES/EN, biblioteca de crucigramas, progreso local, cuentas opcionales con sincronización, PWA instalable |

Hay **preguntas que necesito que me respondas** (sección 9) antes de empezar,
sobre todo presupuesto, uso de IA de pago y qué repositorio usar.

---

## 1. DECISIÓN 1 — Cómo generar los crucigramas

Se tratan por separado los dos problemas que pides, más una idea que los une:
**una palabra solo debe entrar en la cuadrícula si sabemos escribirle una buena
pista.** Por eso el relleno se hace sobre un "léxico con pista posible", no
sobre el diccionario completo.

### 1A. Rellenar la cuadrícula

**Contexto importante.** Los crípticos británicos usan cuadrículas "con
bloques" donde aproximadamente la mitad de las letras de cada palabra no se
cruzan con otra palabra ("unches"). Eso hace el relleno **mucho más fácil** que
en las cuadrículas americanas (todas las letras cruzadas), y permite usar solo
palabras comunes, también en español.

| Opción | Cómo funciona | Ventajas | Inconvenientes | Coste |
|---|---|---|---|---|
| **A. Plantillas + relleno con restricciones** (recomendada) | Se genera una vez una biblioteca de patrones de casillas negras con simetría rotacional de 180°, conectados, palabras de ≥3 letras y ~45–55 % de letras cruzadas. Después se rellenan con búsqueda con retroceso: elegir siempre el hueco con menos candidatos, propagar restricciones a los cruces, preferir palabras frecuentes y prohibir repeticiones (también de la misma raíz: CAMIÓN y CAMIONES). | Rápido, determinista con semilla, fácil de testear. Las plantillas se validan una vez. | Menos variedad de formas que generar el patrón a la vez que el relleno (se compensa con muchas plantillas). | Solo CPU, segundos por cuadrícula. |
| B. Generar patrón y relleno a la vez | Se colocan palabras y bloques sobre la marcha. | Más variedad. | Mucho más difícil garantizar simetría y buena proporción de cruces; más difícil de testear. | CPU, más tiempo. |
| C. Estilo americano (todas las letras cruzadas) | Igual que A pero sin casillas sueltas. | Más "difícil" para el jugador. | Obliga a usar palabras raras para que el relleno sea posible; empeora la calidad. No es el estilo británico. | — |

Reglas que el rellenador debe cumplir y que tendrán tests: simetría, ninguna
palabra repetida (ni raíz repetida), todas las palabras del léxico permitido, sin
palabras ofensivas, número máximo de palabras "poco comunes" por cuadrícula.

**Respuestas de varias palabras** (enumeración "(4,3)"): la v1 se limita a
palabras sueltas y a una lista pequeña de expresiones de varias palabras sacadas
de los recursos de la sección 1D. La enumeración se calcula automáticamente a
partir de la respuesta (espacios → comas, guiones → "-").

### 1B. Escribir las pistas crípticas

Una pista críptica tiene **definición** (al principio o al final) + **juego de
palabras** + **enumeración**. Ejemplo en inglés, respuesta LISTEN:
*"Pay attention to silent rearrangement (6)"* → definición "Pay attention",
anagrama de SILENT, indicador "rearrangement".

Tipos que contemplo: anagrama, palabra oculta, contenedor (A dentro de B),
iniciales/finales (acróstico), homófono, charada (A + B), inversión, supresión
y doble definición. Los indicadores ("rearrangement", "revuelto", "al revés"…)
y las abreviaturas habituales ("norte" → N, "river" → R) los **escribiremos
nosotros** en listas propias, revisadas a mano.

| Opción | Cómo funciona | Ventajas | Inconvenientes | Coste |
|---|---|---|---|---|
| **Basado en reglas** | Para cada respuesta se buscan todas las descomposiciones posibles (anagramas de otras palabras o expresiones, palabras ocultas a lo largo de frases reales, charadas con abreviaturas…). La definición sale de un tesauro. La frase se monta con plantillas gramaticales. | Gratis. Cada pista es correcta por construcción y su solución se puede explicar. Sin dependencias externas. | Las frases suenan artificiales: es el problema clásico (en el sistema ENIGMA de D. Hardcastle, la gente distinguía la pista humana de la generada el 75 % de las veces). En español hay que cuidar concordancias de género y número. Bastante trabajo. | 0 € por crucigrama. |
| **Solo IA vía API** | Se pide a un modelo de lenguaje "escribe una pista críptica para X". | Frases naturales y con gracia. Poco código. | **No es fiable en la parte mecánica**: los modelos cuentan mal letras (anagramas con letras de más o de menos, palabras ocultas que no están). Los estudios recientes muestran que, aunque los modelos han mejorado al *resolver* crípticos, siguen fallando al identificar el tipo de juego de palabras. Validar con otra IA es caro y poco fiable. Es más difícil en español. | ~1–4 USD por 15×15 (ver abajo), con muchos descartes. |
| **Mixto** (recomendado) | 1) Las **reglas** generan el "esqueleto": tipo, material (p. ej. las letras del anagrama), definiciones candidatas e indicadores permitidos. 2) La **IA** solo redacta la frase superficial usando ese material y devuelve un JSON que dice qué tramo del texto es la definición, el indicador y el material. 3) Un **verificador determinista** comprueba el JSON contra el texto. 4) Un segundo modelo **resuelve a ciegas** (sin ver la respuesta) para medir si la pista se puede resolver. 5) Se puntúa y se queda la mejor. Si nada pasa los filtros, queda la versión por reglas o se cambia la palabra. | Corrección mecánica garantizada **y** frase natural. Cada pista lleva su explicación, que se puede mostrar al jugador. Si la API falla o sube de precio, las reglas siguen funcionando. | Más piezas que las otras dos opciones. Dependencia de un proveedor de IA (aislada detrás de una interfaz para poder cambiarlo). | ~0,5–3 USD por 15×15 en lote; ~0,3–1,3 USD por 9×9. |

**Estimación de coste del enfoque mixto** (precios de lista de Anthropic a
14-10-2026, por millón de tokens de entrada/salida: gama media 2/10 USD, gama
alta 4/20 USD, gama ligera 0,10/0,50 USD; la API de lotes cuesta un 50 % menos):

- Redacción: 1 llamada por respuesta que produce 5 candidatas (≈3 000 tokens de
  entrada, en buena parte cacheables, y ≈2 500 de salida) → ≈0,03 USD con gama media.
- Resolución a ciegas de las 2 mejores (≈600 tokens de entrada y ≈2 000 de
  salida cada una) → ≈0,04 USD con gama media u ≈0,09 con gama alta.
- Con un 50 % de reintentos y la rebaja por lotes: **≈0,05–0,10 USD por
  respuesta**. Un 9×9 tiene unas 12–16 respuestas y un 15×15 unas 28–32.
- Ejemplo: 1 crucigrama 9×9 al día en cada idioma ≈ 60 al mes ≈ **20–80 USD/mes**.

Son estimaciones; en la Fase 5 se medirá el coste real por crucigrama y se
guardará en un registro. No se lanza ninguna generación con IA sin que
apruebes antes el presupuesto.

**Cómo se valida que una pista es correcta y resoluble (enfoque mixto):**

1. *Mecánica (determinista)*: las letras del anagrama coinciden exactamente; la
   palabra oculta aparece en el texto cruzando límites de palabra; el contenedor
   o la charada reconstruyen la respuesta; el indicador está en nuestra lista y
   corresponde al tipo; la definición está al principio o al final; la
   enumeración coincide; la respuesta (o su raíz) no aparece en el texto.
2. *Definición*: tiene que ser un sinónimo de la respuesta en el tesauro, con la
   misma categoría gramatical y la misma forma (plural con plural, infinitivo con
   infinitivo). Los casos dudosos van a un juez de IA y, si no está seguro, se descartan.
3. *Solución única*: se buscan alternativas de forma determinista (p. ej. otros
   anagramas del mismo material con la misma enumeración que también encajen con
   la definición) → si hay, se descarta. Las letras cruzadas de la cuadrícula
   ayudan a desambiguar aún más.
4. *Resolubilidad*: el solucionador a ciegas debe llegar a la respuesta y
   explicar el juego de palabras en al menos 1 de 2 intentos. Un fallo del
   solucionador descarta pistas que quizá eran buenas; se acepta, porque
   descartar sale barato.

### 1C. Generar por adelantado o al momento

| Opción | Ventajas | Inconvenientes | Coste |
|---|---|---|---|
| **Por adelantado, en lote** (recomendada) | Coste controlado y predecible; se filtra y se revisa antes de publicar; funciona sin conexión; todos los usuarios ven el mismo crucigrama (se puede hablar de "el n.º 42"); servidor trivial (ficheros JSON en una CDN); la API de lotes es un 50 % más barata. | Hay que programar tareas de generación (p. ej. semanal con GitHub Actions). | Hosting estático gratuito o casi. |
| Al momento | Variedad infinita. | Esperas de segundos o minutos; coste por cada usuario que pide (incluido el abuso); no se puede revisar antes; requiere backend con clave de API y límites de uso. | Proporcional al uso, sin techo. |
| Híbrido (reserva pre-generada que se rellena cuando baja) | Combina ambos. | Complejidad sin beneficio claro en la v1. | — |

Cada crucigrama publicado es **inmutable** y tiene un id estable más una huella
del contenido; el progreso del usuario se guarda por id. Si un crucigrama se
corrige, se publica con un id nuevo.

### 1D. Listas de palabras y diccionarios de sinónimos

Solo uso recursos cuya licencia permite usarlos en una app pública. "SA"
(ShareAlike) significa que **los datos derivados** (no el código de la app)
deben publicarse con la misma licencia; lo marco como pregunta en la sección 9.

**Inglés**

| Recurso | Para qué | Licencia | ¿Usar? |
|---|---|---|---|
| SCOWL (Spell Checker Oriented Word Lists) | Léxico base con niveles de "comunidad" y variantes británicas/americanas | Permisiva (aviso de copyright; uso, copia y redistribución sin coste) | Sí |
| Open English WordNet | Sinónimos, sentidos (dobles definiciones), expresiones de varias palabras | CC BY 4.0 | Sí |
| Moby Thesaurus II | Sinónimos amplios (con ruido) | Dominio público | Sí, como apoyo |
| CMU Pronouncing Dictionary | Homófonos | Permisiva tipo BSD | Sí |
| wordfreq | Frecuencia de uso (para "palabras comunes") | Datos CC BY-SA 4.0; congelado desde ~2021 | Sí (frecuencias estables bastan) |
| Wiktionary (extracto de kaikki.org) | Categoría gramatical, flexiones, sinónimos | CC BY-SA 4.0 | Opcional |
| Collins Scrabble Words, NASPA, XWord Info | Listas de crucigramistas | Comerciales | **No** |
| Spread the Wordlist, lista de P. Broda, UKACD | Listas de crucigramistas | No pude verificar licencia para app pública | **No**, salvo permiso por escrito |

**Español**

| Recurso | Para qué | Licencia | ¿Usar? |
|---|---|---|---|
| Diccionario Hunspell es (proyecto RLA-ES) | Léxico con flexiones (plurales, conjugaciones) y variantes regionales | Triple: GPL-3.0+ / LGPL-3.0+ / MPL-1.1 (según metadatos de distribuciones; se verificará en el repositorio original) | Sí |
| Tesauro es (mythes-es, RLA-ES) | Sinónimos | LGPL-3.0+ (versiones antiguas LGPL-2+) | Sí |
| WordNet español del MCR 3.0 | Sentidos y sinónimos alineados con WordNet inglés | CC BY 3.0 (los datos en inglés, bajo licencia WordNet) | Sí |
| wordfreq (es) | Frecuencia de uso | CC BY-SA 4.0 | Sí |
| Wiktionary es (kaikki.org) | Categorías, flexiones, sinónimos | CC BY-SA 4.0 | Opcional |
| Diccionario de la RAE (DLE), corpus CREA/CORPES | Referencia | Derechos reservados / condiciones de uso restrictivas | **No** (ni extraer datos de la web) |

**Ambos idiomas**: lista LDNOOBW de palabras malsonantes (CC BY 4.0, incluye
`es` y `en`; licencia comprobada en réplicas, se verificará en el original) +
listas propias de palabras vetadas y "sensibles" + listas propias de
indicadores y abreviaturas.

Los ficheros de licencia se guardarán en `data/licenses/` y habrá un `NOTICE`
con las atribuciones, visible también en la app ("Créditos").

**Riesgo específico del español**: el críptico de estilo británico casi no
tiene tradición en español (sí existe el "crucigrama de autor" con definiciones
ingeniosas, p. ej. el de Tarkus). No hay corpus de pistas en español del que
aprender ni convenciones de indicadores asentadas: las crearemos nosotros. Es
probable que la calidad en español vaya por detrás del inglés al principio.

### 1E. Cómo garantizar la calidad

- **Por palabra (antes de rellenar)**: frecuencia mínima, no vetada, no nombre
  propio (en la v1), y al menos *k* esqueletos de pista posibles.
- **Por pista**: los 4 controles de la sección 1B + revisión de ofensividad del
  texto completo de la pista (lista + clasificador de IA), porque una pista
  inocente puede formar una frase ofensiva.
- **Por crucigrama** (se rechaza si falla algún umbral): variedad de tipos (p.
  ej. ≤30 % anagramas, ≥4 tipos distintos), sin indicadores repetidos, sin
  raíces repetidas, frecuencia media mínima de las respuestas, tasa de acierto
  del solucionador a ciegas y una dificultad estimada.
- **Informe por lote**: un HTML con cada crucigrama, sus pistas, sus
  explicaciones y sus métricas, para revisar a mano por muestreo antes de
  publicar.
- **Conjunto de referencia**: un pequeño conjunto de pistas verificadas a mano
  (buenas y malas) que se usa en los tests para que el verificador no empeore.
- **Después de publicar** (propuesto para la v1, ver sección 3): botón "reportar
  pista", anónimo, para retirar crucigramas con problemas.

### 1F. Tamaño inicial

| Opción | Ventajas | Inconvenientes |
|---|---|---|
| 7×7 | Rápido para desarrollar y testear todo el proceso | Muy pocas pistas; poco satisfactorio como juego |
| **9×9 en la v1** (recomendada) | 12–16 pistas: un "mini críptico" de 10–20 min; coste bajo; menos puntos de fallo; cabe bien en 360 px | No es el formato clásico |
| 13×13 / 15×15 | Formato clásico ("quick cryptic" / diario) | 2–3 veces más pistas que salir bien y más caro; se activa cuando las métricas de 9×9 sean buenas |

El código (plantillas, relleno, interfaz) se diseña para cualquier tamaño desde
el principio; solo cambia qué se publica.

---

## 2. DECISIÓN 2 — Plataforma y tecnologías

| Opción | Ventajas | Inconvenientes | Coste |
|---|---|---|---|
| **A. PWA (web instalable)** (recomendada para la v1) | Un solo código; actualizaciones inmediatas; funciona sin conexión con *service worker*; sin tiendas ni revisiones; una cuadrícula y el teclado son terreno natural de la web. | En iOS la instalación es manual ("Añadir a pantalla de inicio"); Safari puede borrar datos locales de webs no usadas en días (las apps instaladas parecen exentas, pero no está documentado: se mitiga pidiendo almacenamiento persistente y con la sincronización por cuenta); sin presencia en tiendas. | Hosting estático gratuito (p. ej. Cloudflare Pages). |
| B. React Native/Expo compartiendo código con la web | App nativa real; buena presencia en tiendas. | La web generada con react-native-web es menos "web"; la cuadrícula y la entrada de teclado se implementan dos veces en la práctica; compilaciones nativas (EAS) y más herramientas que mantener. | Tiendas: Apple 99 USD/año, Google 25 USD una vez; compilaciones en la nube con capa gratuita limitada. |
| C. Capacitor envolviendo la PWA | Mismo código que A; presencia en tiendas; almacenamiento nativo (sin borrados de Safari); acceso a "Sign in with Apple" nativo. | Apple puede rechazar apps que "solo son una web" (directriz 4.2): hay que aportar valor (sin conexión, teclado propio, etc.); revisiones de tienda en cada versión nativa. | Igual que B en tiendas. |

**Recomendación**: **A en la v1, preparada para C** en una fase posterior sin
reescribir nada. B solo compensaría si la experiencia nativa fuera prioritaria
sobre la web, y no es el caso para un juego de cuadrícula.

**Stack propuesto** (cada dependencia se justificará de nuevo al añadirla):

| Pieza | Elección | Por qué |
|---|---|---|
| Lenguaje | **TypeScript en todo** (app, lógica y generador) | El formato de crucigrama, la normalización de letras (Ñ, tildes) y las reglas del juego se escriben una vez y se usan en el generador y en la app. Alternativa: generador en Python (más librerías de lenguaje natural), a cambio de duplicar código. Si algún recurso solo se puede extraer cómodamente con Python, se usará un script puntual de preparación de datos, documentado. |
| Monorepo | pnpm workspaces | Paquetes separados (`core`, `generator`, `web`) con instalación rápida y sin herramientas extra. |
| Interfaz | React + Vite | El ecosistema más amplio y fácil de mantener; Vite compila rápido; funciona con Capacitor. |
| PWA | vite-plugin-pwa (Workbox) | Manifiesto y *service worker* estándar sin escribirlos a mano. |
| Almacenamiento local | IndexedDB con un envoltorio mínimo (idb-keyval o propio) | Más robusto que localStorage para el progreso. |
| Idiomas de la interfaz | Diccionarios JSON propios y una función `t()` | Dos idiomas no justifican una librería grande. |
| Tests | Vitest (unitarios), Testing Library (componentes), Playwright (extremo a extremo, ya instalado en el entorno) | Estándar con Vite; Playwright permite probar a 360 px y con teclado. |
| Accesibilidad | axe-core en los tests de Playwright | Detecta automáticamente errores de accesibilidad comunes. |
| Calidad de código | ESLint + Prettier + `tsc --noEmit` en CI | Que cada fase "compile y pase tests" de forma comprobable. |
| CI | GitHub Actions | El repositorio ya está en GitHub; también sirve para programar la generación por lotes. |
| IA (solo generador) | SDK oficial del proveedor elegido detrás de una interfaz propia | Poder cambiar de proveedor o funcionar sin IA. La app nunca llama a la IA. |

---

## 3. DECISIÓN 3 — Alcance de la versión 1

**Entra en la v1**

- Crucigramas crípticos 9×9 en español e inglés, generados en lote, con
  explicación de cada pista (se ve al revelar o al terminar).
- Biblioteca de crucigramas filtrable por idioma; completados tachados o con
  marca ✓, empezados con "a medias" y su porcentaje.
- Resolver: todo lo de la sección 6 (cuadrícula, pistas, teclado físico y en
  pantalla, comprobar y revelar letra, palabra o todo).
- Progreso local sin cuenta. Cuenta opcional (email con código) con
  sincronización y fusión del progreso; exportar y borrar la cuenta desde la app.
- Interfaz en español e inglés (elegible, con el idioma del navegador por defecto).
- PWA instalable y uso sin conexión de los crucigramas ya descargados.
- Generación semanal automática + informe de calidad para revisión.
- README (arrancar, generar, desplegar), política de privacidad y créditos de datos.
- Botón "reportar pista" anónimo (opcional; confírmalo en la sección 9).

**Queda para después** (en orden de prioridad que propongo)

1. 13×13 y luego 15×15.
2. Apps en tiendas con Capacitor; "Sign in with Apple" y Google.
3. Crucigrama del día y rachas.
4. Niveles de dificultad y pistas intermedias (p. ej. "mostrar la definición").
5. Modo lápiz, temporizador con estadísticas, imprimir.
6. Panel web de revisión editorial (en la v1 basta el informe HTML).
7. Notificaciones, clasificaciones y funciones sociales.

---

## 4. Cuentas de usuario, backend y privacidad

### Arquitectura

- **Crucigramas**: ficheros JSON estáticos en la misma CDN que la web, más un
  índice (catálogo). Ningún servidor interviene para jugar.
- **Progreso local primero**: la app siempre lee y escribe en IndexedDB. Con
  cuenta, además sincroniza en segundo plano. Sin conexión, la sincronización
  queda pendiente y se reintenta.

### Opciones de backend para cuentas y progreso

| Opción | Ventajas | Inconvenientes | Coste |
|---|---|---|---|
| **Supabase** (recomendada) | Postgres + autenticación + reglas de acceso por fila (cada usuario solo ve lo suyo); región UE (Fráncfort); de código abierto (se puede autoalojar si hiciera falta salir); acuerdo de tratamiento de datos (DPA) disponible. | Los proyectos gratuitos se pausan tras una semana sin actividad → en producción conviene el plan Pro. El email que incluye tiene límites → hace falta un proveedor SMTP (p. ej. Resend o Brevo, con capa gratuita). | 0 USD en desarrollo; **25 USD/mes** en producción (Pro: hasta 100 000 usuarios activos al mes). SMTP: 0 USD con poco volumen. |
| Firebase (Google) | Capa gratuita amplia sin pausas; sincronización sin conexión de Firestore. | Base de datos documental propietaria y dependencia de Google; reglas de seguridad menos expresivas que SQL. | 0 USD probablemente durante mucho tiempo; luego, pago por uso. |
| Backend propio (Cloudflare Workers + D1 + email) | El más barato y con todo el control. | Hay que escribir y mantener la autenticación (riesgo de seguridad) y más código. | 0–5 USD/mes. |

Los precios de Supabase proceden de guías de terceros de 2026; se comprobarán en
supabase.com/pricing antes de contratar.

### Método de acceso

**Código de un solo uso enviado por email** (6 dígitos), en lugar de enlace
mágico. En una PWA de iOS, el enlace del correo se abre en Safari y no en la app
instalada, y la sesión se queda en otro sitio; el código se teclea dentro de la
app. Sin contraseñas que guardar ni recuperar. Google y Apple quedan para
después (si la app de iOS ofreciera Google, Apple exige además una opción
equivalente que respete la privacidad; en la práctica, "Sign in with Apple").

### Datos que se guardan (mínimos)

- Cuenta: email, identificador interno y fecha de alta. Ni nombre, ni foto, ni
  fecha de nacimiento.
- Progreso, por crucigrama: id del crucigrama, letras escritas, casillas
  reveladas o comprobadas, estado (sin empezar / a medias / completado), fechas
  de inicio, última modificación y fin, y tiempo de juego.
- Reportes de pistas (si se aprueban): id de pista, motivo y fecha, **sin**
  vincular al usuario.
- Sin analítica con cookies ni rastreadores en la v1. Si más adelante se quiere
  analítica, una sin cookies (p. ej. Plausible o Umami autoalojado).

### Fusión del progreso al iniciar sesión (sin perder nada)

Reglas para cada crucigrama, aplicadas por una función del servidor en una sola
transacción (así dos dispositivos a la vez no se pisan):

1. Si solo existe en un lado → se copia al otro.
2. Estado: gana el "más avanzado" (completado > a medias > sin empezar).
   Fecha de completado: la más temprana.
3. Si uno está completado → sus letras son las finales.
4. Si los dos están a medias → casilla por casilla: una letra gana a una casilla
   vacía; si hay dos letras distintas, gana la del registro modificado más
   recientemente. Las marcas de "revelada" o "comprobada" se suman (si está en
   un lado, queda en el resultado). Tiempo de juego: el mayor.
5. Nunca se borra progreso al fusionar. Cerrar sesión deja el progreso local
   tal como esté.

Esta lógica vive en `core`, con tests de todos los casos, y la función del
servidor aplica la misma regla.

### RGPD y privacidad

- Base jurídica: ejecución del servicio que el usuario pide (art. 6.1.b RGPD)
  para la cuenta. Guardar progreso en el dispositivo es funcionalidad pedida por
  el usuario y no requiere consentimiento de cookies; sin rastreadores **no hace
  falta banner de cookies**.
- Datos alojados en la UE; DPA firmado con Supabase y con el proveedor de email.
- Derechos: exportar mis datos (JSON) y borrar la cuenta desde la app, sin
  pasar por soporte. El borrado elimina el progreso del servidor.
- Conservación: propuesta de borrar las cuentas sin uso en 24 meses, avisando antes.
- Edad mínima: en España, 14 años para consentir. Como no usamos consentimiento
  sino contrato, propongo exigir 14 años en los términos; conviene revisión legal.
- Política de privacidad y aviso legal: los necesitan el nombre del
  responsable (persona o empresa); ver pregunta en la sección 9.
- Los crucigramas los genera la IA en nuestro servidor de generación; **ningún
  dato de usuario se envía a la IA**.

---

## 5. Idioma, Ñ, tildes y diéresis

- **Interfaz** en español e inglés, elegible e independiente del idioma de los
  crucigramas.
- **Alfabeto de la cuadrícula**: inglés A–Z; español A–Z + **Ñ** (27 letras).
- **Tildes y diéresis** (convención habitual de los crucigramas en español): en
  la cuadrícula se ignoran. Á→A, É→E, Í→I, Ó→O, Ú→U, Ü→U. La **Ñ es una letra
  distinta** de la N: escribir N donde va Ñ es un error al comprobar.
- **CH y LL** ocupan dos casillas (no son letras desde 2010).
- Cada respuesta se guarda de dos formas: normalizada para la cuadrícula
  (`CAMION`) y con su ortografía correcta para mostrar en la explicación
  (`camión`). La enumeración cuenta letras normalizadas.
- **Entrada**:
  - Teclado físico: se acepta "á", "ä", "à"… y se convierten a la letra base;
    "ñ" se acepta en teclados españoles; en un teclado inglés, el teclado en
    pantalla tiene tecla Ñ.
  - Móvil: **teclado propio en pantalla** (QWERTY con Ñ en los crucigramas en
    español). Evita el autocorrector y las sugerencias, que la pantalla salte al
    abrir el teclado y que la Ñ dependa del teclado del sistema. Las teclas son
    botones accesibles para lectores de pantalla y se puede seguir usando el
    teclado físico o uno bluetooth.
- Las pistas se escriben con ortografía correcta (tildes incluidas). El
  verificador cuenta letras sin tildes: en un anagrama, "camión" aporta las
  letras C-A-M-I-O-N.
- Toda esta normalización está en `core`, con tests específicos.

---

## 6. Experiencia de resolver

Mínimo que pides, más ajustes que propongo (**en negrita**):

- Cuadrícula con casilla activa y palabra activa resaltadas; lista de pistas
  horizontales y verticales con la activa resaltada; tocar una pista lleva a su
  palabra. **En móvil, la pista activa se muestra en una barra sobre el teclado**
  y la lista completa en otra pestaña o desplegable.
- Teclado físico: letras, retroceso (borra y retrocede), flechas, **espacio o
  tocar la casilla activa para cambiar de dirección**, **Tab/Mayús+Tab para
  pasar de pista**, saltar casillas ya rellenas al escribir.
- Comprobar y revelar: letra, palabra y todo. Las letras erróneas se marcan; las
  reveladas quedan marcadas para siempre. **Al revelar una palabra se muestra la
  explicación de su pista** (definición subrayada, tipo de juego de palabras).
- Al completar: mensaje de enhorabuena, todas las explicaciones visibles, y el
  crucigrama queda marcado como completado en la lista. **Si se usó "revelar",
  queda como "completado con ayuda"** (icono distinto); confírmalo en la sección 9.
- **Guardado automático** continuo; volver a un crucigrama deja todo como estaba.
- 360 px: un 9×9 cabe con casillas de ~36 px; un 15×15 con casillas de ~22 px
  (usable, sin zoom). Sin desplazamiento horizontal.
- Accesibilidad: navegación completa con teclado; lectura por lector de
  pantalla de "casilla 3 de 5, 7 horizontal, pista…"; contraste AA; modo oscuro;
  respetar "reducir movimiento" y el tamaño de letra del sistema.

---

## 7. Arquitectura y calidad

```
/packages/core        Lógica pura: formato del crucigrama, normalización por idioma,
                      navegación, comprobar/revelar, fin de partida, fusión de progreso.
                      Sin dependencias de interfaz. Tests unitarios.
/packages/generator   CLI de Node: léxicos, plantillas, rellenador, motor de juegos de
                      palabras, verificador, cliente de IA, puntuación, informe HTML.
/apps/web             React + Vite + PWA. Solo interfaz y almacenamiento.
/data                 Scripts de descarga y preparación de recursos, licencias y NOTICE.
/content              Crucigramas publicados (JSON) y catálogo.
/supabase             Migraciones SQL, reglas de acceso y función de fusión.
/docs                 Esta propuesta y decisiones posteriores.
```

- Formato del crucigrama versionado (con esquema JSON validado en los tests):
  id, idioma, tamaño, casillas negras, entradas (número, dirección, casillas,
  respuesta normalizada, forma para mostrar, enumeración, pista, explicación) y
  metadatos del generador (versión, semilla, métricas). Las respuestas se
  guardan ligeramente codificadas para que no se vean por accidente; no es
  seguridad, solo evitar *spoilers*.
- Cada fase termina con: `tsc` sin errores, lint, tests verdes y un commit con
  resumen de lo hecho y lo pendiente.

---

## 8. Plan por fases

Cada fase es pequeña y termina en un commit que compila y pasa los tests.

| Fase | Contenido | Resultado comprobable |
|---|---|---|
| 0 | Esqueleto del monorepo, TypeScript, lint, Vitest, CI en GitHub Actions, README inicial | `pnpm test` y CI en verde |
| 1 | `core`: formato del crucigrama, normalización ES/EN (Ñ, tildes), modelo de cuadrícula, navegación, comprobar/revelar, fin de partida, fusión de progreso | Tests unitarios de todo, incluidos los casos de Ñ y la fusión |
| 2 | Datos: scripts de descarga de recursos, construcción del léxico por idioma (frecuencia, vetos, normalización), licencias y NOTICE | Léxicos generados reproduciblemente; tests sobre muestras |
| 3 | Plantillas simétricas y rellenador para 7×7 y 9×9 | Tests de simetría, sin repeticiones y palabras del léxico; prueba de tiempo |
| 4 | Motor de juegos de palabras por reglas, verificador, comprobación de unicidad, explicaciones, abreviaturas e indicadores propios | Un crucigrama completo **sin IA** de principio a fin; conjunto de referencia en tests |
| 5 | Redacción con IA, solucionador a ciegas, puntuación, lotes, registro de coste, informe HTML. **Requiere tu clave de API y aprobar presupuesto** | Primer lote de 9×9 en ES y EN con métricas y coste real medido |
| 6 | Web: biblioteca y pantalla de juego (cuadrícula, pistas, teclado físico), progreso local, marcas de completado o a medias, interfaz ES/EN | Tests de componentes y de Playwright jugando un crucigrama entero |
| 7 | Móvil y PWA: teclado en pantalla con Ñ, diseño a 360 px, instalación y uso sin conexión, revisión de accesibilidad con axe | Tests de Playwright a 360 px; auditoría de accesibilidad sin errores |
| 8 | Cuentas y sincronización: Supabase (UE), acceso con código por email, tabla de progreso con acceso por fila, función de fusión, exportar y borrar, política de privacidad | Tests de fusión contra una base de datos local de Supabase; prueba extremo a extremo de iniciar sesión con progreso previo |
| 9 | Despliegue: Cloudflare Pages, generación semanal programada, reportar pista, README completo (arrancar, generar, desplegar) | Web pública v1 |
| 10+ | 13×13 → 15×15, Capacitor y tiendas, resto de la lista "para después" | — |

Las fases 2–5 (generador) y la 6 (web, con crucigramas de ejemplo escritos a
mano solo como datos de test) son independientes. Si prefieres ver la app
antes, puedo hacer la 6 justo después de la 1.

---

## 9. Preguntas que necesito que respondas

1. **Presupuesto mensual** aproximado para hosting, backend, IA y, en su caso,
   tiendas. Con esto decido entre plan gratuito o de pago y el ritmo de generación.
2. **¿Apruebas usar una API de IA de pago** en la generación (enfoque mixto)?
   ¿Tienes ya cuenta o clave de API? Sin IA, la v1 sería solo con pistas por
   reglas (correctas, pero con frases más rígidas).
3. **¿Usamos este repositorio** (`hdiazalex/-roblox`) o prefieres uno nuevo con
   otro nombre? ¿Tienes nombre o dominio para la app?
4. **Variedad de idioma**: ¿español de España o neutro? ¿Inglés británico (lo
   natural en crípticos: *colour*) o americano?
5. **Público**: ¿principiantes en crípticos (explicaciones visibles, pistas
   más fáciles) o aficionados expertos?
6. **Ritmo de publicación**: ¿biblioteca que crece (p. ej. X por semana) o un
   crucigrama del día? ¿Cuántos al mes por idioma?
7. **¿Necesitas estar en App Store / Google Play en la v1**, o basta la PWA?
8. **Monetización o analítica**: ¿habrá anuncios, pagos o analítica? Afecta a
   RGPD (consentimiento) y a la arquitectura.
9. **Revisión humana**: ¿alguien revisará los lotes antes de publicarse o debe
   ser 100 % automático?
10. **Licencias**: ¿aceptas publicar los léxicos derivados bajo CC BY-SA (por
    usar wordfreq/Wiktionary)? ¿El código de la app será abierto o privado?
11. **Responsable legal** para la política de privacidad: ¿persona física o
    empresa, y de qué país?
12. **Ayudas**: un crucigrama terminado usando "revelar", ¿cuenta como
    completado normal o como "completado con ayuda"?
13. **"Reportar pista"** anónimo en la v1: ¿sí o no?

---

## 10. Riesgos principales

| Riesgo | Mitigación |
|---|---|
| Calidad de las pistas en español (sin tradición ni corpus) | Enfoque mixto, listas propias de indicadores, revisión por muestreo, empezar en 9×9 |
| La IA genera pistas incorrectas | Nunca se confía en ella para la mecánica: verificador determinista + solucionador a ciegas |
| Coste de la IA mayor de lo estimado | Lotes con 50 % de descuento, medición en la Fase 5, tope de gasto, y recurso a las pistas por reglas |
| Safari borra datos locales | Almacenamiento persistente, cuenta con sincronización, y Capacitor si hiciera falta |
| Licencias mal interpretadas | Verificar cada `LICENSE` original en la Fase 2; descartar recursos dudosos |
| Palabras o frases ofensivas | Vetos en el léxico + revisión del texto completo de la pista + reportes |

---

## Fuentes consultadas

- Precios de la API de Claude: documentación de Anthropic (tabla de modelos y
  API de lotes, octubre de 2026).
- Supabase: [JetAdmin 2026](https://www.jetadmin.io/blog/supabase-pricing-2026-guide-to-plans-limits-and-real-world-costs/), [Schematic](https://schematichq.com/blog/supabase-pricing), [AutomationAtlas](https://automationatlas.io/answers/supabase-pricing-explained-2026/) (secundarias).
- WordNet español del MCR: [TALP-UPC](https://talp.cs.upc.edu/content/spanish-and-catalan-wordnets-0.html), [adimen EHU](https://adimen.ehu.eus/web/MCR), [arXiv 2107.00333](https://arxiv.org/abs/2107.00333v2).
- Open English WordNet: [Oxford Text Archive 2024](https://llds.ling-phil.ox.ac.uk/llds/xmlui/handle/20.500.14106/2571-2024).
- Hunspell es / RLA-ES: [CERN repoview](https://linuxsoft.cern.ch/cern/centos/7/updates/x86_64/repoview/hunspell-es.html); tesauro: [Arch mythes-es](https://archlinux.org/packages/extra/any/mythes-es/).
- wordfreq: [PyPI](https://pypi.org/project/wordfreq).
- SCOWL: [Debian copyright](https://sources.debian.org/src/scowl/7.1-1/Copyright/).
- LDNOOBW: [README](https://raw.githubusercontent.com/LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words/master/README.md).
- Listas de crucigramistas: [Shopping for Wordlists](https://tcampbell.substack.com/p/shopping-for-wordlists), [NASPA Licensing](https://naspa.games/w/Licensing).
- Generación de pistas por reglas (ENIGMA, Hardcastle): [ACL W07-2323](https://aclanthology.org/W07-2323.xml), [Crossword Unclued](https://www.crosswordunclued.com/2012/02/can-computer-program-write-cryptic.html), [Cambridge talk](https://talks.cam.ac.uk/talk/index/10735/).
- Modelos de lenguaje y crípticos: [Sadallah et al., COLING 2025 (arXiv 2412.09012)](https://www.arxiv.org/pdf/2412.09012), [Saha et al., NAACL 2025](https://aclanthology.org/2025.naacl-long.104), [arXiv 2406.09043](https://arxiv.org/abs/2406.09043).
- PWA en iOS: [Apple Developer Forums](https://developer.apple.com/forums/thread/710157), [WebKit bug 232302](https://bugs.webkit.org/show_bug.cgi?id=232302), [Ionic](https://ionic.io/blog/is-apple-trying-to-kill-pwas).
- Directriz 4.8 de Apple: [OpenStreetMap #2799](https://lists.openstreetmap.org/pipermail/rails-dev/2025-May/040605.html), [WorkOS](https://workos.com/blog/apple-app-store-authentication-sign-in-with-apple-2025).
- Crucigrama en español: [elDiario.es, "Elogio del crucigrama"](https://www.eldiario.es/cultura/elogio-crucigrama_1_12194868.html).
