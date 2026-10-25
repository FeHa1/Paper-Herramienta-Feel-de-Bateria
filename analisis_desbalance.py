"""Sensibilidad al desbalance (rock y bateristas) a partir de los CSV de analisis_feel.py.
Uso: python3 analisis_desbalance.py puntajes_completa.csv puntajes_solo_media.csv
"""
import sys
import pandas as pd
from scipy.stats import wilcoxon


def tasa(d, k):
    return 100 * (d["A"] > d[k]).mean()


def informe(nombre, d):
    print(f"\n===== {nombre} (n={len(d)})")
    pares = ["B", "C", "D"]
    por_gen = pd.DataFrame({k: d.groupby("genero").apply(lambda s: tasa(s, k)) for k in pares})
    por_gen["n"] = d.groupby("genero").size()
    por_bat = pd.DataFrame({k: d.groupby("baterista").apply(lambda s: tasa(s, k)) for k in pares})
    print("\nTasa de aciertos por género (%):\n", por_gen.round(0).to_string())
    filas = {
        "Ponderado por ejecución": {k: tasa(d, k) for k in pares},
        "Promedio por género": por_gen[pares].mean().to_dict(),
        "Sin rock": {k: tasa(d[d.genero != "rock"], k) for k in pares},
        "Sin drummer7": {k: tasa(d[d.baterista != "drummer7"], k) for k in pares},
        "Promedio por baterista": por_bat.mean().to_dict(),
    }
    jk = pd.DataFrame({b: {k: tasa(d[d.baterista != b], k) for k in pares}
                       for b in sorted(d.baterista.unique())}).T
    filas["Jackknife (mín)"] = jk.min().to_dict()
    filas["Jackknife (máx)"] = jk.max().to_dict()
    print("\nTasas A>B, A>C, A>D (%) según agregación:\n", pd.DataFrame(filas).T.round(0).to_string())
    print("\nNivel baterista (n=10), Wilcoxon bilateral sobre la diferencia media A-k:")
    for k in pares:
        dif = d.assign(x=d["A"] - d[k]).groupby("baterista")["x"].mean()
        print(f"  A-{k}: media={dif.mean():.1f}, bateristas con A>{k}: {(dif > 0).sum()}/10, p={wilcoxon(dif).pvalue:.3g}")
    r = d[d.genero == "rock"]
    print("\nRock por baterista (n y % A>D):\n",
          r.groupby("baterista").apply(lambda s: pd.Series({"n": len(s), "A>D": tasa(s, "D")})).round(0).to_string())
    m = d[d.baterista.isin(r.baterista.unique())].assign(rock=lambda x: x.genero == "rock")
    print("\nMismo baterista, rock vs no-rock (% A>D):\n",
          m.groupby(["baterista", "rock"]).apply(lambda s: tasa(s, "D")).unstack().round(0).to_string())


if __name__ == "__main__":
    for nombre, ruta in zip(["Métrica completa", "Solo media"], sys.argv[1:3]):
        informe(nombre, pd.read_csv(ruta))
