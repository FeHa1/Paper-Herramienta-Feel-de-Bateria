"""
Analisis de microtiming sobre el Groove MIDI Dataset (Etapa 1 de validacion).

Uso:
    python analisis_feel.py --dataset ./groove
    python analisis_feel.py --dataset ./groove --solo-media
    python analisis_feel.py --dataset ./groove --generos funk,jazz,rock

Salidas:
    - Diagnostico y conteos por consola
    - Filas LaTeX listas para pegar en las tablas del paper
    - puntajes.csv con el puntaje de cada ejecucion en cada condicion
"""
import argparse
import os
from collections import defaultdict

import numpy as np
import pandas as pd
import pretty_midi
from scipy.stats import wilcoxon

# ---------------------------------------------------------------- parametros
PASOS_POR_COMPAS = 16          # grilla de semicorcheas en 4/4
MIN_NOTAS_CELDA = 4            # notas minimas de una ejecucion en una celda
MIN_EJEC_CELDA = 3             # ejecuciones de referencia minimas por celda
TAU_MIN = 0.02                 # piso para la dispersion de medias (fraccion de semicorchea)
RHO_MIN = 0.10                 # piso para la dispersion de log-desvio
SD_PISO = 0.005                # desvio minimo (evita log(0) en la version cuantizada)
SEMILLA = 42

# Mapeo de notas MIDI del Roland TD-11 (Groove MIDI Dataset) a instrumento
INSTRUMENTO = {
    36: "bombo",
    38: "redoblante", 40: "redoblante", 37: "redoblante",
    42: "hihat", 22: "hihat", 44: "hihat", 46: "hihat", 26: "hihat",
    51: "ride", 59: "ride", 53: "ride",
}


def rango_tempo(bpm):
    if bpm < 90:
        return "lento"
    if bpm <= 120:
        return "medio"
    return "rapido"


# ---------------------------------------------------------------- extraccion
def extraer_desvios(ruta_midi, bpm):
    """Devuelve {(instrumento, posicion): [desvios en fraccion de semicorchea]}
    y la lista de desvios en ms."""
    pm = pretty_midi.PrettyMIDI(ruta_midi)
    paso = 60.0 / bpm / 4.0  # duracion de una semicorchea en segundos
    celdas = defaultdict(list)
    desvios_ms = []
    for inst in pm.instruments:
        for nota in inst.notes:
            nombre = INSTRUMENTO.get(nota.pitch)
            if nombre is None:
                continue
            k = int(round(nota.start / paso))
            desvio = (nota.start - k * paso) / paso
            celdas[(nombre, k % PASOS_POR_COMPAS)].append(desvio)
            desvios_ms.append(desvio * paso * 1000)
    return {c: np.array(v) for c, v in celdas.items()}, np.array(desvios_ms)


def resumir(celdas):
    """Media y desvio por celda (solo celdas con suficientes notas)."""
    out = {}
    for c, d in celdas.items():
        if len(d) >= MIN_NOTAS_CELDA:
            out[c] = (d.mean(), max(d.std(), SD_PISO), len(d))
    return out


# ---------------------------------------------------------------- perfil
def construir_perfil(ejecuciones):
    """Perfil por celda y por rango de tempo, con respaldo a 'todos' los tempos."""
    acumulado = defaultdict(lambda: {"medias": [], "logsd": []})
    for e in ejecuciones:
        for c, (m, sd, _) in e["resumen"].items():
            for clave in [(c, e["rango"]), (c, "todos")]:
                acumulado[clave]["medias"].append(m)
                acumulado[clave]["logsd"].append(np.log(sd))
    perfil = {}
    for clave, v in acumulado.items():
        if len(v["medias"]) >= MIN_EJEC_CELDA:
            perfil[clave] = (
                np.mean(v["medias"]),
                max(np.std(v["medias"]), TAU_MIN),
                np.mean(v["logsd"]),
                max(np.std(v["logsd"]), RHO_MIN),
            )
    return perfil


def puntaje(resumen, rango, perfil, solo_media):
    """Puntaje de cercania 0-100 (ver ecuacion en la seccion de diseño)."""
    total, peso = 0.0, 0
    for c, (m, sd, n) in resumen.items():
        ref = perfil.get((c, rango)) or perfil.get((c, "todos"))
        if ref is None:
            continue
        mu, tau, lsd, rho = ref
        s = np.exp(-0.5 * ((m - mu) / tau) ** 2)
        if not solo_media:
            s *= np.exp(-0.5 * ((np.log(sd) - lsd) / rho) ** 2)
        total += n * s
        peso += n
    return 100 * total / peso if peso else np.nan


# ---------------------------------------------------------------- condiciones
def cuantizada(celdas):
    return {c: np.zeros_like(d) for c, d in celdas.items()}


def aleatoria(celdas, rng):
    todos = np.concatenate(list(celdas.values()))
    sd = todos.std()
    return {c: np.clip(rng.normal(0, sd, len(d)), -0.5, 0.5) for c, d in celdas.items()}


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, help="carpeta que contiene info.csv")
    ap.add_argument("--generos", default="", help="lista separada por comas (por defecto: automática)")
    ap.add_argument("--solo-media", action="store_true", help="puntaje sin el término de dispersión")
    args = ap.parse_args()
    rng = np.random.default_rng(SEMILLA)

    info = pd.read_csv(os.path.join(args.dataset, "info.csv"))
    print("Columnas de info.csv:", list(info.columns))
    total_archivos = len(info)
    info = info[(info["beat_type"] == "beat") & (info["time_signature"] == "4-4")].copy()
    info["genero"] = info["style"].str.split("/").str[0]
    print(f"Archivos totales: {total_archivos} | beats en 4/4: {len(info)}")

    # Seleccion de generos
    resumen_gen = info.groupby("genero").agg(archivos=("id", "count"), bateristas=("drummer", "nunique"))
    print("\nArchivos y bateristas por género:\n", resumen_gen.sort_values("archivos", ascending=False))
    if args.generos:
        generos = [g.strip() for g in args.generos.split(",")]
    else:
        ok = resumen_gen[(resumen_gen["bateristas"] >= 3) & (resumen_gen["archivos"] >= 15)]
        generos = list(ok.index)
    print("\nGéneros analizados:", generos)
    info = info[info["genero"].isin(generos)]

    # Extraccion
    ejecuciones, todos_ms, todos_frac = [], [], []
    for _, fila in info.iterrows():
        ruta = os.path.join(args.dataset, fila["midi_filename"])
        try:
            celdas, ms = extraer_desvios(ruta, fila["bpm"])
        except Exception as ex:
            print("Error leyendo", ruta, ex)
            continue
        res = resumir(celdas)
        if not res:
            continue
        ejecuciones.append({
            "id": fila["id"], "baterista": fila["drummer"], "genero": fila["genero"],
            "bpm": fila["bpm"], "rango": rango_tempo(fila["bpm"]),
            "celdas": celdas, "resumen": res,
        })
        todos_ms.append(ms)
        todos_frac.append(np.concatenate(list(celdas.values())))
    todos_ms = np.concatenate(todos_ms)
    todos_frac = np.concatenate(todos_frac)

    # Diagnostico de alineacion: si la grilla esta bien, la mayoria de los
    # desvios deberian estar cerca de 0 (|desvio| < 0.25 semicorchea).
    cerca = np.mean(np.abs(todos_frac) < 0.25)
    print(f"\nDIAGNÓSTICO: {cerca:.1%} de los golpes a menos de 1/4 de semicorchea de la grilla "
          f"(con desvíos al azar sería ~50%). Desvío medio global: {todos_ms.mean():.1f} ms.")
    if cerca < 0.7:
        print("  ATENCIÓN: la alineación con la grilla parece dudosa. Revisar antes de usar resultados.")

    bpms = [e["bpm"] for e in ejecuciones]
    print(f"\nDatos analizados: {len(ejecuciones)} ejecuciones, "
          f"{len(set(e['baterista'] for e in ejecuciones))} bateristas, "
          f"tempos {min(bpms)}-{max(bpms)} BPM, {len(todos_ms)} golpes.")

    # Validacion cruzada dejando un baterista afuera
    filas = []
    for baterista in sorted(set(e["baterista"] for e in ejecuciones)):
        referencia = [e for e in ejecuciones if e["baterista"] != baterista]
        perfiles = {g: construir_perfil([e for e in referencia if e["genero"] == g]) for g in generos}
        for e in (x for x in ejecuciones if x["baterista"] == baterista):
            g, r = e["genero"], e["rango"]
            if not perfiles[g]:
                continue
            a = puntaje(e["resumen"], r, perfiles[g], args.solo_media)
            b = puntaje(resumir(cuantizada(e["celdas"])), r, perfiles[g], args.solo_media)
            c = puntaje(resumir(aleatoria(e["celdas"], rng)), r, perfiles[g], args.solo_media)
            otros = [puntaje(e["resumen"], r, perfiles[o], args.solo_media)
                     for o in generos if o != g and perfiles[o]]
            d = np.nanmean(otros) if otros else np.nan
            filas.append({"id": e["id"], "baterista": baterista, "genero": g,
                          "A": a, "B": b, "C": c, "D": d})

    df = pd.DataFrame(filas).dropna(subset=["A", "B", "C"])
    df.to_csv("puntajes.csv", index=False)
    print(f"\nEjecuciones evaluadas: {len(df)} (guardado en puntajes.csv)")

    # ---------------- Tabla 1: puntaje medio (desvio)
    print("\n% ---- Tabla 1: puntaje medio (desvío estándar) ----")
    grupos = [(g, df[df["genero"] == g]) for g in generos] + [("Global", df)]
    for nombre, sub in grupos:
        if sub.empty:
            continue
        celdas = " & ".join(f"{sub[k].mean():.1f} ({sub[k].std():.1f})" for k in "ABCD")
        print(f"{nombre.capitalize()} & {celdas} \\\\")

    # ---------------- Tabla 2: tasa de aciertos por pares
    print("\n% ---- Tabla 2: tasa de aciertos (n) ----")
    for nombre, sub in grupos:
        if sub.empty:
            continue
        partes = []
        for k in "BCD":
            s = sub.dropna(subset=[k])
            partes.append(f"{100 * (s['A'] > s[k]).mean():.0f}\\,\\%")
        print(f"{nombre.capitalize()} (n={len(sub)}) & " + " & ".join(partes) + " \\\\")

    # ---------------- Test estadistico (global)
    print("\nTest de Wilcoxon (global, pareado, A vs cada condición):")
    for k in "BCD":
        s = df.dropna(subset=[k])
        if len(s) > 10:
            stat, p = wilcoxon(s["A"], s[k])
            print(f"  A vs {k}: diferencia media = {(s['A'] - s[k]).mean():.1f} puntos, p = {p:.2g}, n = {len(s)}")

    # ---------------- Tabla 3: perfil descriptivo en ms
    print("\n% ---- Tabla 3 (opcional): desvío medio en ms por género e instrumento ----")
    for g in generos:
        valores = []
        for inst in ["bombo", "redoblante", "hihat", "ride"]:
            ms = []
            for e in (x for x in ejecuciones if x["genero"] == g):
                paso_ms = 60.0 / e["bpm"] / 4.0 * 1000
                for (nombre, _), d in e["celdas"].items():
                    if nombre == inst:
                        ms.append(d * paso_ms)
            ms = np.concatenate(ms) if ms else np.array([])
            valores.append(f"{ms.mean():+.1f} ({ms.std():.1f})" if len(ms) else "--")
        print(f"{g.capitalize()} & " + " & ".join(valores) + " \\\\")


if __name__ == "__main__":
    main()
