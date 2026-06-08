"""
Protótipo de modelos "nota esperada de exame", treinados de forma
segmentada (ciclo básico vs. secundário) sobre os CSVs já limpos e
normalizados gerados por preparar_dados_aval.py.

Abordagem (espelha o modelo de notas internas já existente em analytics.py,
mas treinado e validado separadamente para cada grupo de exame):

  Variáveis preditoras (todas na escala 0-20, calculadas a partir da
  própria linha + contexto, SEM usar a nota de exame doutros alunos da
  mesma linha):
    x1 = média das notas periódicas internas do aluno nessa disciplina/ano
    x2 = CIF do aluno nessa disciplina/ano (classificação interna final;
         usa-se x1 como proxy quando o CIF não existe)
    x3 = média de exame da turma, nessa disciplina/ano (contexto local,
         excluindo a própria observação)
    x4 = média de exame do nível/ano de escolaridade, nessa disciplina/ano
         (contexto mais amplo — corrige variações de dificuldade da prova)

  nota_exame_esperada = b0 + b1*x1 + b2*x2 + b3*x3 + b4*x4

Validação: divisão treino/teste 80/20 (aleatória, com seed fixa), com
métricas de R², MAE (erro médio absoluto) e desvio-padrão dos resíduos —
tanto no treino como no teste, para se perceber se o modelo generaliza.

NOTA: isto é um protótipo para avaliar viabilidade e fiabilidade da
abordagem — não substitui o modelo de produção, que teria de ser integrado
em analytics.py com a mesma disciplina de cache/circularidade aí aplicada.
"""

from __future__ import annotations

import csv
import random
from collections import defaultdict

import numpy as np

SEED = 42
FICHEIROS = {
    "ciclo":      "exames_ciclo_basico.csv",
    "secundario": "exames_secundario.csv",
}


def carregar(ficheiro):
    linhas = []
    with open(ficheiro, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                r["nota_exame_norm_0_20"] = float(r["nota_exame_norm_0_20"])
            except (TypeError, ValueError):
                continue
            for campo in ("nota_p1", "nota_p2", "nota_p3", "cif"):
                v = r.get(campo)
                r[campo] = float(v) if v not in (None, "", "None") else None
            linhas.append(r)
    return linhas


def media_periodica(linha):
    vals = [linha[c] for c in ("nota_p1", "nota_p2", "nota_p3") if linha[c] is not None]
    return (sum(vals) / len(vals)) if vals else None


def construir_features(linhas, grupo):
    """Calcula x1..x4 para cada linha, excluindo sempre a própria observação
    do cálculo dos contextos de turma/nível (evita circularidade)."""

    # Pré-agregações para os contextos (turma e nível), por (chave, disciplina, ano)
    por_turma = defaultdict(list)   # (turma, disciplina, ano_letivo) -> [(idx, nota_norm)]
    por_nivel = defaultdict(list)   # (nivel, ano_turma, disciplina, ano_letivo) -> [(idx, nota_norm)]

    for i, l in enumerate(linhas):
        chave_turma = (l["turma"], l["disciplina"], l["ano_letivo"])
        chave_nivel = (l["nivel"], l["ano_turma"], l["disciplina"], l["ano_letivo"])
        por_turma[chave_turma].append((i, l["nota_exame_norm_0_20"]))
        por_nivel[chave_nivel].append((i, l["nota_exame_norm_0_20"]))

    def media_excluindo(grupo_idx_notas, idx_proprio):
        vals = [n for j, n in grupo_idx_notas if j != idx_proprio]
        return (sum(vals) / len(vals)) if vals else None

    X, y, validas = [], [], []
    for i, l in enumerate(linhas):
        x1 = media_periodica(l)
        if x1 is None:
            continue
        x2 = l["cif"] if l["cif"] is not None else x1

        chave_turma = (l["turma"], l["disciplina"], l["ano_letivo"])
        chave_nivel = (l["nivel"], l["ano_turma"], l["disciplina"], l["ano_letivo"])
        x3 = media_excluindo(por_turma[chave_turma], i)
        x4 = media_excluindo(por_nivel[chave_nivel], i)

        if x3 is None and x4 is None:
            continue
        if x3 is None:
            x3 = x4
        if x4 is None:
            x4 = x3

        X.append([x1, x2, x3, x4])
        y.append(l["nota_exame_norm_0_20"])
        validas.append(l)

    return np.array(X, dtype=float), np.array(y, dtype=float), validas


def treinar_e_validar(X, y, grupo):
    n = len(y)
    if n < 40:
        print(f"[{grupo}] dados insuficientes ({n} observações) — não é possível treinar/validar com confiança.")
        return

    rng = random.Random(SEED)
    indices = list(range(n))
    rng.shuffle(indices)
    corte = int(n * 0.8)
    idx_treino, idx_teste = indices[:corte], indices[corte:]

    X_tr, y_tr = X[idx_treino], y[idx_treino]
    X_te, y_te = X[idx_teste], y[idx_teste]

    # OLS via mínimos quadrados (numpy) — equivalente às equações normais
    # já usadas em analytics.py, mas com resolução numericamente mais estável
    design_tr = np.column_stack([np.ones(len(X_tr)), X_tr])
    coefs, *_ = np.linalg.lstsq(design_tr, y_tr, rcond=None)

    def prever(X_):
        design = np.column_stack([np.ones(len(X_)), X_])
        pred = design @ coefs
        return np.clip(pred, 0.0, 20.0)

    pred_tr = prever(X_tr)
    pred_te = prever(X_te)

    def metricas(y_real, y_prev):
        residuos = y_real - y_prev
        sqt = np.sum((y_real - y_real.mean()) ** 2)
        sqr = np.sum(residuos ** 2)
        r2 = 1 - sqr / sqt if sqt > 0 else float("nan")
        mae = np.mean(np.abs(residuos))
        return r2, mae, residuos.std(ddof=1) if len(residuos) > 1 else float("nan")

    r2_tr, mae_tr, std_tr = metricas(y_tr, pred_tr)
    r2_te, mae_te, std_te = metricas(y_te, pred_te)

    print(f"\n=== Modelo '{grupo}' ===")
    print(f"  Observações utilizáveis: {n}  (treino={len(idx_treino)}, teste={len(idx_teste)})")
    print(f"  Coeficientes [b0, b1(periodica), b2(CIF), b3(turma), b4(nivel)]:")
    print(f"    {np.round(coefs, 3).tolist()}")
    print(f"  Treino  -> R²={r2_tr:.3f}  MAE={mae_tr:.2f}  desvio-resíduos={std_tr:.2f}")
    print(f"  Teste   -> R²={r2_te:.3f}  MAE={mae_te:.2f}  desvio-resíduos={std_te:.2f}")

    if r2_te < 0.1:
        print("  AVISO: R² no teste muito baixo — o modelo explica pouco da variação;")
        print("         as variáveis disponíveis podem não ser suficientes para prever bem este grupo.")
    elif r2_tr - r2_te > 0.15:
        print("  AVISO: queda acentuada de R² treino->teste — possível sobreajuste (overfitting),")
        print("         ou amostra de teste pequena/pouco representativa.")
    else:
        print("  -> desempenho consistente entre treino e teste (sem sinais óbvios de sobreajuste).")


def main():
    for grupo, ficheiro in FICHEIROS.items():
        linhas = carregar(ficheiro)
        # Para já, deixar de fora os anos atípicos (pandemia) na validação do secundário
        linhas_uteis = [l for l in linhas if l.get("epoca_atipica") not in ("True", True)]
        X, y, validas = construir_features(linhas_uteis, grupo)
        print(f"[{grupo}] linhas no CSV: {len(linhas)} | após filtrar anos atípicos: {len(linhas_uteis)} "
              f"| com features completas: {len(y)}")
        treinar_e_validar(X, y, grupo)


if __name__ == "__main__":
    main()
