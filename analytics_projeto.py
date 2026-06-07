"""
Motor de análise da Avaliação de Projeto (área admin, só leitura).

Três níveis de visão, todos centrados na tabela `projeto_avaliacao`
(+ `projeto_grupos` / `projeto_grupo_membros` para contexto de grupo/tema):

  1. resumo_global(db)        — visão de todo o 11º ano
  2. resumo_turma(db, turma)  — visão de uma turma
  3. analise_aluno_projeto(db, aluno_id) — ficha individual

Sem dependências externas (só `statistics`), seguindo o padrão de `analytics.py`.
"""

import statistics
from collections import defaultdict

ANO_LETIVO = "2025/2026"

# Componentes da avaliação de projeto, na ordem em que devem ser apresentados.
# (chave na tabela projeto_avaliacao, rótulo para a interface, escala máxima)
COMPONENTES = [
    ("media_workshops",         "Workshops",                 5),
    ("desempenho_aula",         "Desempenho em aula",        5),
    ("apresentacao_oral_qo",    "Apresentação Oral (QO)",    20),
    ("poster",                  "Póster",                    20),
    ("questionario",            "Questionário",              20),
    ("artigo",                  "Artigo",                    20),
    ("media_componentes",       "Média dos Componentes",     20),
    ("apresentacao_final",      "Apresentação Final",        20),
    ("avaliacao_produto_final", "Avaliação do Produto Final",20),
    ("avaliacao_final",         "Avaliação Final",           20),
]
COMPONENTE_PRINCIPAL = "avaliacao_final"


def _round1(x):
    return round(x, 1) if x is not None else None


# ─── Carregamento de dados ────────────────────────────────────────────────────

def carregar_avaliacoes(db, ano_letivo=ANO_LETIVO):
    """Lista de dicts: dados do aluno + todas as componentes de projeto."""
    rows = db.execute("""
        SELECT pa.*, a.id AS aluno_id, a.numero, a.nome, a.turma
        FROM projeto_avaliacao pa
        JOIN alunos a ON a.id = pa.aluno_id
        WHERE pa.ano_letivo = ?
        ORDER BY a.turma, a.nome
    """, (ano_letivo,)).fetchall()
    return [dict(r) for r in rows]


def carregar_grupos(db, ano_letivo=ANO_LETIVO):
    """dict aluno_id -> {grupo, tema, questao_orientadora, estado_aprovacao,
                          professor_orientador, colegas:[{id,nome,turma}]}"""
    grupos = db.execute("""
        SELECT * FROM projeto_grupos WHERE ano_letivo=?
    """, (ano_letivo,)).fetchall()

    info_por_aluno = {}
    for g in grupos:
        membros = db.execute("""
            SELECT a.id, a.nome, a.turma FROM projeto_grupo_membros m
            JOIN alunos a ON a.id = m.aluno_id
            WHERE m.grupo_id = ?
            ORDER BY a.nome
        """, (g["id"],)).fetchall()
        membros = [dict(m) for m in membros]
        for m in membros:
            colegas = [c for c in membros if c["id"] != m["id"]]
            info_por_aluno[m["id"]] = {
                "grupo_numero":         g["numero"],
                "sala":                 g["sala"],
                "tema":                 g["tema"],
                "questao_orientadora":  g["questao_orientadora"],
                "estado_aprovacao":     g["estado_aprovacao"],
                "professor_orientador": g["professor_orientador"],
                "colegas":              colegas,
            }
    return info_por_aluno


# ─── Estatísticas auxiliares ──────────────────────────────────────────────────

def _stats(valores):
    valores = [v for v in valores if v is not None]
    if not valores:
        return {"n": 0, "media": None, "mediana": None, "minimo": None, "maximo": None, "desvio": None}
    return {
        "n":       len(valores),
        "media":   _round1(statistics.mean(valores)),
        "mediana": _round1(statistics.median(valores)),
        "minimo":  _round1(min(valores)),
        "maximo":  _round1(max(valores)),
        "desvio":  _round1(statistics.pstdev(valores)) if len(valores) > 1 else 0.0,
    }


def _agrupar_por(avaliacoes, chave):
    grupos = defaultdict(list)
    for av in avaliacoes:
        grupos[av[chave]].append(av)
    return grupos


def _outliers(avaliacoes, componente=COMPONENTE_PRINCIPAL, limiar_z=1.5):
    """Alunos cujo valor no `componente` se desvia >= limiar_z desvios-padrão
    da média do conjunto. Devolve (excelencias, alertas) ordenados por |z| desc."""
    valores = [av[componente] for av in avaliacoes if av[componente] is not None]
    if len(valores) < 2:
        return [], []
    media = statistics.mean(valores)
    desvio = statistics.pstdev(valores)
    if desvio == 0:
        return [], []

    excelencias, alertas = [], []
    for av in avaliacoes:
        v = av[componente]
        if v is None:
            continue
        z = (v - media) / desvio
        if z >= limiar_z:
            excelencias.append({**av, "z": round(z, 2)})
        elif z <= -limiar_z:
            alertas.append({**av, "z": round(z, 2)})
    excelencias.sort(key=lambda x: -x["z"])
    alertas.sort(key=lambda x: x["z"])
    return excelencias, alertas


def _ranking_grupos(avaliacoes_por_chave, componente=COMPONENTE_PRINCIPAL, n_min=1):
    """A partir de {chave: [avaliações]}, devolve lista ordenada por média
    decrescente: [{chave, n, media, mediana, desvio}]"""
    linhas = []
    for chave, avs in avaliacoes_por_chave.items():
        if chave is None:
            continue
        valores = [av[componente] for av in avs if av[componente] is not None]
        if len(valores) < n_min:
            continue
        linhas.append({
            "chave":   chave,
            "n":       len(valores),
            "media":   _round1(statistics.mean(valores)),
            "mediana": _round1(statistics.median(valores)),
            "desvio":  _round1(statistics.pstdev(valores)) if len(valores) > 1 else 0.0,
        })
    linhas.sort(key=lambda x: -(x["media"] or 0))
    for i, l in enumerate(linhas, start=1):
        l["posicao"] = i
    return linhas


def _distribuicao_niveis(avaliacoes, chave_nivel="desempenho_aula_nivel"):
    contagem = defaultdict(int)
    for av in avaliacoes:
        nivel = av.get(chave_nivel)
        if nivel:
            contagem[nivel] += 1
    return dict(sorted(contagem.items(), key=lambda kv: -kv[1]))


def _comparacao_componentes(avaliacoes):
    """Para cada componente, estatísticas globais — permite ver onde a turma/
    o ano é mais forte ou mais fraco."""
    linhas = []
    for chave, rotulo, escala in COMPONENTES:
        valores = [av[chave] for av in avaliacoes if av.get(chave) is not None]
        if not valores:
            continue
        st = _stats(valores)
        linhas.append({
            "chave": chave, "rotulo": rotulo, "escala": escala,
            **st,
            "media_pct": round(100 * st["media"] / escala) if st["media"] is not None else None,
        })
    return linhas


# ─── Nível 1: visão global do 11º ano ────────────────────────────────────────

def resumo_global(db, ano_letivo=ANO_LETIVO):
    avaliacoes = carregar_avaliacoes(db, ano_letivo)
    if not avaliacoes:
        return None

    grupos_info = carregar_grupos(db, ano_letivo)

    por_turma = _agrupar_por(avaliacoes, "turma")
    ranking_turmas = _ranking_grupos(por_turma)

    # Agrupar por professor orientador / tema (via info de grupo de cada aluno)
    por_orientador, por_tema = defaultdict(list), defaultdict(list)
    for av in avaliacoes:
        info = grupos_info.get(av["aluno_id"])
        if info:
            if info["professor_orientador"]:
                por_orientador[info["professor_orientador"]].append(av)
            if info["tema"]:
                # encurtar tema para etiqueta
                tema_curto = (info["tema"][:70] + "…") if len(info["tema"]) > 70 else info["tema"]
                por_tema[tema_curto].append(av)

    excelencias, alertas = _outliers(avaliacoes)

    return {
        "n_alunos":            len(avaliacoes),
        "n_turmas":            len(por_turma),
        "geral":               _stats([av[COMPONENTE_PRINCIPAL] for av in avaliacoes]),
        "componentes":         _comparacao_componentes(avaliacoes),
        "ranking_turmas":      ranking_turmas,
        "ranking_orientadores":_ranking_grupos(por_orientador, n_min=2),
        "ranking_temas":       _ranking_grupos(por_tema, n_min=2),
        "distribuicao_niveis": _distribuicao_niveis(avaliacoes),
        "excelencias":         excelencias[:15],
        "alertas":             alertas[:15],
    }


# ─── Nível 2: visão por turma ────────────────────────────────────────────────

def resumo_turma(db, turma, ano_letivo=ANO_LETIVO):
    todas = carregar_avaliacoes(db, ano_letivo)
    if not todas:
        return None
    da_turma = [av for av in todas if av["turma"] == turma]
    if not da_turma:
        return None

    grupos_info = carregar_grupos(db, ano_letivo)

    geral_ano = _stats([av[COMPONENTE_PRINCIPAL] for av in todas])
    geral_turma = _stats([av[COMPONENTE_PRINCIPAL] for av in da_turma])

    # tabela de alunos ordenada por avaliação final desc, com posição no ano
    valores_ano = sorted([av[COMPONENTE_PRINCIPAL] for av in todas if av[COMPONENTE_PRINCIPAL] is not None], reverse=True)
    alunos = []
    for av in sorted(da_turma, key=lambda a: (a[COMPONENTE_PRINCIPAL] is None, -(a[COMPONENTE_PRINCIPAL] or 0))):
        v = av[COMPONENTE_PRINCIPAL]
        pos_ano = (valores_ano.index(v) + 1) if v is not None and v in valores_ano else None
        info = grupos_info.get(av["aluno_id"], {})
        alunos.append({**av, "pos_ano": pos_ano, "n_ano": len(valores_ano),
                       "tema": info.get("tema"), "grupo_numero": info.get("grupo_numero")})

    excelencias, alertas = _outliers(da_turma)

    return {
        "turma":               turma,
        "n_alunos":            len(da_turma),
        "geral_turma":         geral_turma,
        "geral_ano":           geral_ano,
        "diferenca_media":     _round1((geral_turma["media"] or 0) - (geral_ano["media"] or 0)) if geral_turma["media"] is not None and geral_ano["media"] is not None else None,
        "componentes":         _comparacao_componentes(da_turma),
        "componentes_ano":     _comparacao_componentes(todas),
        "alunos":              alunos,
        "distribuicao_niveis": _distribuicao_niveis(da_turma),
        "excelencias":         excelencias,
        "alertas":             alertas,
    }


# ─── Nível 3: ficha individual ───────────────────────────────────────────────

def analise_aluno_projeto(db, aluno_id, ano_letivo=ANO_LETIVO):
    todas = carregar_avaliacoes(db, ano_letivo)
    if not todas:
        return None
    av = next((a for a in todas if a["aluno_id"] == aluno_id), None)
    if av is None:
        return None

    turma = av["turma"]
    da_turma = [a for a in todas if a["turma"] == turma]

    componentes = []
    for chave, rotulo, escala in COMPONENTES:
        valor = av.get(chave)
        if valor is None:
            continue
        valores_turma = [a[chave] for a in da_turma if a.get(chave) is not None]
        valores_ano   = [a[chave] for a in todas    if a.get(chave) is not None]
        media_turma = statistics.mean(valores_turma) if valores_turma else None
        media_ano   = statistics.mean(valores_ano) if valores_ano else None
        desvio_ano  = statistics.pstdev(valores_ano) if len(valores_ano) > 1 else 0
        z_ano = ((valor - media_ano) / desvio_ano) if desvio_ano else 0
        pos_turma = 1 + sum(1 for v in valores_turma if v > valor)
        pos_ano   = 1 + sum(1 for v in valores_ano if v > valor)
        componentes.append({
            "chave": chave, "rotulo": rotulo, "escala": escala,
            "valor": _round1(valor),
            "media_turma": _round1(media_turma), "media_ano": _round1(media_ano),
            "pos_turma": pos_turma, "n_turma": len(valores_turma),
            "pos_ano": pos_ano, "n_ano": len(valores_ano),
            "z_ano": round(z_ano, 2),
            "destaque": "excelencia" if z_ano >= 1.5 else ("alerta" if z_ano <= -1.5 else None),
        })

    grupos_info = carregar_grupos(db, ano_letivo)
    grupo = grupos_info.get(aluno_id)

    return {
        "aluno_id":   aluno_id,
        "nome":       av["nome"],
        "numero":     av["numero"],
        "turma":      turma,
        "avaliacao":  av,
        "componentes": componentes,
        "observacao": av.get("observacao"),
        "grupo":      grupo,
    }
