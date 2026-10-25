# Herramienta de "feel" para bateristas

Código del trabajo de investigación **"Herramienta de *feel* para bateristas"**: una métrica que mide qué tan cerca están los desvíos de microtiming de un baterista del perfil estadístico de un género, construido a partir del [Groove MIDI Dataset](https://magenta.tensorflow.org/datasets/groove).

> **Estado:** prototipo de investigación. Este repositorio contiene la métrica y el experimento de validación interna (Etapa 1 del trabajo). **No** es todavía una aplicación para que un baterista suba su propia grabación y reciba un puntaje: la métrica está implementada, pero el script solo evalúa las ejecuciones del propio dataset.

## La idea

Un baterista que toca funk, swing o rock no toca perfectamente "cuadrado" con el metrónomo: adelanta o atrasa ciertos golpes de forma sutil e intencional, y eso le da el *feel* característico al estilo. Las herramientas de evaluación habituales tratan esos desvíos como error y premian la ejecución más cuantizada.

La propuesta es lo contrario: construir, a partir de ejecuciones reales, un **perfil de desvíos por género** y medir qué tan cerca está una ejecución de ese perfil. Una ejecución perfectamente cuantizada, que suena a máquina, debería puntuar mal.

## Cómo funciona

1. **Entrada.** Un archivo MIDI de batería y su tempo.
2. **Alineación a la grilla.** Cada golpe se asigna a la posición de semicorchea más cercana. Con $\Delta = 60/(4\cdot\mathrm{BPM})$ la duración de una semicorchea y $t_i$ el instante del golpe $i$:

   $$k_i = \mathrm{round}(t_i/\Delta), \qquad d_i = \frac{t_i - k_i\Delta}{\Delta} \in [-0{,}5;\,0{,}5]$$

3. **Celdas.** Los golpes se agrupan por *(instrumento, posición en el compás)*: bombo, redoblante, hi-hat y ride, con 16 posiciones por compás de 4/4. Para cada celda $c$ de una ejecución se calcula la media $m_c$, el desvío estándar $s_c$ y la cantidad de golpes $n_c$ de los $d_i$.
4. **Perfil de referencia.** Para cada género, celda y rango de tempo (lento < 90 BPM, medio 90–120, rápido > 120), el perfil guarda la media $\mu_c$ y la dispersión $\tau_c$ de los $m_c$ de las ejecuciones de referencia, y la media $\lambda_c$ y dispersión $\rho_c$ de $\ln s_c$.
5. **Puntaje de cercanía.**

   $$S = 100\cdot\frac{\sum_c n_c\, e^{-\frac12\left(\frac{m_c-\mu_c}{\tau_c}\right)^2}\, e^{-\frac12\left(\frac{\ln s_c-\lambda_c}{\rho_c}\right)^2}}{\sum_c n_c}$$

   El primer factor mide si los desvíos **sistemáticos** coinciden con los del género; el segundo, si la **variabilidad** es comparable. $S$ vale 100 cuando la ejecución coincide con el perfil en todas las celdas.

## Qué devuelve

La métrica devuelve un **puntaje de 0 a 100** por ejecución. Como cada término de la suma es la contribución de una celda, el puntaje se puede descomponer por instrumento y posición (el script actual solo reporta el puntaje global).

El script `analisis_feel.py` aplica la métrica a todo el dataset con **validación cruzada dejando un baterista afuera** y compara cuatro condiciones para cada ejecución `x`:

| Condición | Descripción |
|---|---|
| **A, original** | `x` sin modificar |
| **B, cuantizada** | todos los desvíos llevados a cero |
| **C, aleatoria** | desvíos de media cero y la misma dispersión global que `x`, sin estructura por instrumento ni posición |
| **D, género cruzado** | `x` puntuada contra cada uno de los otros perfiles, promediando |

La hipótesis es que A obtiene un puntaje mayor que B y que C. Salidas:

- Diagnóstico y conteos por consola (archivos, géneros, bateristas, golpes).
- Filas de LaTeX con el puntaje medio y la tasa de aciertos por pares (tablas del paper).
- Tests de Wilcoxon pareados (bilaterales) de A contra B, C y D.
- Desvío medio en ms por género e instrumento.
- `puntajes.csv`: un puntaje por ejecución, con columnas `id, baterista, genero, A, B, C, D`.

## Resultado principal

La hipótesis se cumple solo en parte. Con la métrica completa, la ejecución original supera a la cuantizada, pero únicamente porque el término de dispersión asigna puntaje nulo a toda ejecución sin variabilidad. Al conservar solo el término de media, la cuantizada queda más cerca del perfil que la original en rock. La métrica tampoco distingue de forma consistente los desvíos originales de los aleatorios, y la especificidad de los perfiles se concentra en rock, latin y jazz. Con solo 10 bateristas, repartidos de forma desigual entre géneros, no se puede separar el efecto del género del efecto del baterista. Los detalles, las tablas y el análisis de sensibilidad al desbalance están en el paper.

## Uso

### Requisitos

Python 3 y estos paquetes:

```bash
python3 -m venv .venv
source .venv/bin/activate        # en Windows: .venv\Scripts\activate
python -m pip install numpy pandas scipy pretty_midi
```

### Datos

Descargá la versión 1.0.0 (solo MIDI) del Groove MIDI Dataset desde la [página de Magenta](https://magenta.tensorflow.org/datasets/groove) y descomprimila. El dataset no está incluido en este repositorio. El script necesita la carpeta que contiene `info.csv`.

### Análisis principal

```bash
python3 analisis_feel.py --dataset ./groove
python3 analisis_feel.py --dataset ./groove --solo-media
python3 analisis_feel.py --dataset ./groove --generos funk,jazz,rock
```

- `--dataset`: carpeta que contiene `info.csv` (obligatorio).
- `--solo-media`: puntaje sin el término de dispersión.
- `--generos`: lista de géneros separada por comas. Por defecto se incluyen los que tienen al menos 3 bateristas y 15 archivos de patrones en 4/4.

El script no muestra progreso y tarda unos minutos, porque procesa unos 430 archivos MIDI. **Cada corrida sobrescribe `puntajes.csv`**: guardá cada variante con otro nombre antes de volver a correr.

```bash
python3 analisis_feel.py --dataset ./groove && cp puntajes.csv puntajes_completa.csv
python3 analisis_feel.py --dataset ./groove --solo-media && cp puntajes.csv puntajes_solo_media.csv
```

### Análisis de sensibilidad al desbalance

A partir de los dos CSV, sin volver a correr el experimento:

```bash
python3 analisis_desbalance.py puntajes_completa.csv puntajes_solo_media.csv
```

Calcula las tasas de aciertos promediando por género y por baterista, sin rock, sin `drummer7` y excluyendo a cada baterista, además del test de Wilcoxon con el baterista como unidad y la comparación dentro de cada baterista para rock.

## Decisiones de preprocesamiento

- Se usan solo los archivos `beat` (sin *fills*) en compás 4/4. El tempo y el género salen de los metadatos; el género es la primera parte de la etiqueta de estilo.
- Notas MIDI por instrumento: bombo (36), redoblante (37, 38, 40), hi-hat (22, 26, 42, 44, 46) y ride (51, 53, 59). Toms y *crash* se ignoran.
- La grilla se alinea con el inicio del archivo, suponiendo que el metrónomo comienza en el primer tiempo en $t=0$.
- Se usan las celdas con al menos 4 golpes por ejecución. Una celda entra al perfil si la comparten al menos 3 ejecuciones del mismo rango de tempo; si no, se usa el perfil con todos los tempos, y si tampoco alcanza, no se puntúa.
- Pisos numéricos: 0,005 para $s_c$, 0,02 para $\tau_c$ y 0,10 para $\rho_c$.
- La condición C usa una sola realización por ejecución, con semilla 42 y bateristas procesados en orden alfabético.
- La partición original del dataset (entrenamiento, validación, prueba) no se usa: la validación cruzada por baterista la reemplaza.

## Limitaciones

- Mide solo microtiming; excluye dinámica y timbre.
- Solo MIDI; no procesa audio.
- Grilla de semicorcheas rectas: no representa bien a los géneros con subdivisión ternaria (swing, *shuffle*).
- El Groove MIDI Dataset tiene 10 bateristas (5 profesionales y 5 aficionados), grabados en un kit electrónico con metrónomo y sin banda, con más dispersión que las grabaciones comerciales.
- Los datos están desbalanceados: rock aporta el 42 % de las ejecuciones evaluadas y un solo baterista (`drummer7`) el 26 %.
- La validación con oyentes expertos (Etapa 2) está pendiente.

## Archivos

| Archivo | Contenido |
|---|---|
| `analisis_feel.py` | métrica, perfiles, condiciones A–D y validación cruzada |
| `analisis_desbalance.py` | análisis de sensibilidad al desbalance a partir de los CSV |
| `puntajes_completa.csv` | puntajes por ejecución, métrica completa |
| `puntajes_solo_media.csv` | puntajes por ejecución, variante solo media |

## Referencia del dataset

J. Gillick, A. Roberts, J. Engel, D. Eck y D. Bamman, "Learning to groove with inverse sequence transformations", *International Conference on Machine Learning* (PMLR), 2019, pp. 2269–2279.
