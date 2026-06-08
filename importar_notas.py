"""
Script para importar notas dos ficheiros de Avaliação Contínua.
Execute:  python importar_notas.py

Processa automaticamente todos os ficheiros .xlsx na pasta 'notas/'
(ou os ficheiros indicados como argumentos).

Uso:
    python importar_notas.py                        # processa pasta notas/
    python importar_notas.py ficheiro1.xlsx ...     # ficheiros específicos
"""

import sqlite3
import openpyxl
import sys
import os
import glob
import unicodedata
import re

DATABASE  = "portal.db"
ANO_LETIVO = "2025/2026"
SEMESTRE   = 1   # 1º semestre = período 1

# ─── Utilitários ──────────────────────────────────────────────────────────────

def normalizar(s):
    """Remove acentos e converte para minúsculas para comparação fuzzy."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = s.encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()

def parse_nota(v):
    """Converte valor da célula para float ou None."""
    if v is None:
        return None
    s = str(v).strip()
    if s in ("-", "", "NP", "NP.", "NE", "NA", "—"):
        return None
    try:
        return float(s)
    except ValueError:
        return None

def extrair_turma(cell_val):
    """'12 - 12A1 AV' → '12A1 AV'"""
    s = str(cell_val).strip()
    if " - " in s:
        return s.split(" - ", 1)[1].strip()
    return s

# ─── Normalização de nomes de disciplinas ────────────────────────────────────
# Algumas pautas usam abreviaturas ou grafias diferentes para a mesma
# disciplina (ex.: "Econ C" / "ECO. C" para "Economia C", "AI B" / "AP. IN"
# para "Aplicações Informáticas B"). Para que as notas fiquem todas associadas
# à mesma disciplina na BD (nome canónico = o usado em ORDEM_TODAS/ABREVIATURAS
# de app.py), mapeamos aqui as variantes conhecidas para o nome canónico.
# Adicionar novas entradas sempre que surgir uma grafia diferente numa pauta.
DISCIPLINAS_ALIAS = {
    "eco. c":       "Economia C",
    "econ. c":      "Economia C",
    "eco c":        "Economia C",
    "econ c":       "Economia C",
    "eco.c":        "Economia C",
    "econ.c":       "Economia C",
    "eco. a":       "Economia A",
    "econ. a":      "Economia A",
    "eco a":        "Economia A",
    "econ a":       "Economia A",
    "eco.a":        "Economia A",
    "econ.a":       "Economia A",
    "ap. in":       "Aplicações Informáticas B",
    "ap.in":        "Aplicações Informáticas B",
    "ap in":        "Aplicações Informáticas B",
    "ap. inf":      "Aplicações Informáticas B",
    "ap. inf.":     "Aplicações Informáticas B",
    "ap. inf. b":   "Aplicações Informáticas B",   # confirmado em produção (2026-06-08)
    "ap inf b":     "Aplicações Informáticas B",
    "aplic. info":  "Aplicações Informáticas B",
    "aplic. info. b": "Aplicações Informáticas B",
    "aplicacoes informaticas": "Aplicações Informáticas B",
    "aplicacoes informaticas b": "Aplicações Informáticas B",
    "ai b":         "Aplicações Informáticas B",
    "mat. a":       "Matemática A",
    "mat a":        "Matemática A",
    "mat.a":        "Matemática A",   # confirmado em produção (2026-06-08): "MAT.A"
    "mat. b":       "Matemática B",
    "mat b":        "Matemática B",
    "mat.b":        "Matemática B",
    "mat. g":       "Matemática Geral",
    "mat g":        "Matemática Geral",
    "mat.g":        "Matemática Geral",
    "des. a":       "Desenho A",
    "des a":        "Desenho A",
    "des.a":        "Desenho A",
    "des. g":       "Desenho Geral",
    "des g":        "Desenho Geral",
    "des.g":        "Desenho Geral",
    "hist. a":      "História A",
    "hist a":       "História A",
    "hist.a":       "História A",
    "hist. b":      "História B",
    "hist b":       "História B",
    "hist.b":       "História B",
    "hist. g":      "História Geral",
    "hist g":       "História Geral",
    "hist.g":       "História Geral",
    "fis. quim a":  "Física e Química A",
    "fis quim a":   "Física e Química A",
    "fis. quim. a": "Física e Química A",
    "fq a":         "Física e Química A",
    "fq.a":         "Física e Química A",
    "geo. a":       "Geografia A",
    "geo a":        "Geografia A",
    "geo.a":        "Geografia A",
    "ed. fis":      "Educação Física",
    "ed.fis":       "Educação Física",
    "ed fis":       "Educação Física",
    "ed. fis.":     "Educação Física",
    # ATENÇÃO — "Filosofia" / "Filosofia A" são disciplinas DISTINTAS, tal como
    # "Inglês" / "Líng. Estrang. I - Inglês". Grafias curtas como "Fil." ou
    # "Ing." são ambíguas (não dá para saber a qual das duas se referem) —
    # propositadamente NÃO mapeadas aqui, para nunca fundir as erradas.
    # Só incluir alias para estas se a grafia identificar claramente uma delas
    # (ex.: "Fil. A" → "Filosofia A").
    "fil. a":       "Filosofia A",
    "fil a":        "Filosofia A",
    "fil.a":        "Filosofia A",
    "port.":        "Português",
    "port":         "Português",
    "lit.":         "Literacias",
    "lit. p":       "Literatura Portuguesa",
    "lit p":        "Literatura Portuguesa",
    "lit.p":        "Literatura Portuguesa",
    "bio. geo":     "Biologia e Geologia",
    "bio geo":      "Biologia e Geologia",
    "bio.geo":      "Biologia e Geologia",
    "psic. b":      "Psicologia B",
    "psic b":       "Psicologia B",
    "psic.b":       "Psicologia B",
    "c. pol":       "Ciência Política",
    "c pol":        "Ciência Política",
    "c.pol":        "Ciência Política",
    "gda":          "Geometria Descritiva A",
    "macs":         "Matemática Aplicada Ciências Sociais",
    "rel.":         "Religião",
    "rel":          "Religião",
    "alem.":        "Alemão",
    "alem":         "Alemão",
    "esp.":         "Espanhol",
    "esp":          "Espanhol",
    "fr.":          "Francês",
    "fr":           "Francês",
    "proj.":        "Projeto",
    "proj":         "Projeto",
}

def canonizar_disciplina(nome):
    """
    Tenta mapear um nome de disciplina, tal como surge na pauta, para o nome
    canónico usado na BD/portal (as chaves de ABREVIATURAS / ORDEM_TODAS em
    app.py). Cobre variantes de abreviatura, pontuação e maiúsculas/minúsculas
    (ex.: 'ECO. C' e 'Econ C' → 'Economia C'; 'AI B' e 'AP. IN' →
    'Aplicações Informáticas B'). Se não houver alias conhecido, devolve o
    nome original (sem normalizar) para não perder disciplinas novas/raras —
    nesse caso convém acrescentar a variante a DISCIPLINAS_ALIAS.
    """
    if not nome:
        return nome
    chave = normalizar(nome)
    if chave in DISCIPLINAS_ALIAS:
        return DISCIPLINAS_ALIAS[chave]
    # tentar também sem pontuação final (ex.: 'fil.' → 'fil')
    sem_ponto = chave.rstrip(".").strip()
    if sem_ponto in DISCIPLINAS_ALIAS:
        return DISCIPLINAS_ALIAS[sem_ponto]
    return str(nome).strip()

# ─── Parser do ficheiro ────────────────────────────────────────────────────────

def parse_ficheiro(path):
    """
    Devolve lista de dicts:
    {turma, nome_aluno, disciplina, nota, semestre}
    """
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))

    # Encontrar linha com 'Nome Turma' na col 0
    header_idx = None
    for i, row in enumerate(rows):
        if row[0] and "Nome" in str(row[0]) and "Turma" in str(row[0]):
            header_idx = i
            break

    if header_idx is None:
        print(f"  AVISO: estrutura não reconhecida em {os.path.basename(path)}")
        return []

    disc_row  = rows[header_idx - 2]   # linha com nomes das disciplinas
    np_row    = rows[header_idx]        # linha com 'NP.'

    # Construir mapa  disciplina -> índice coluna NP
    disc_cols = sorted([
        i for i, v in enumerate(disc_row)
        if v and str(v).strip()
        and "Nome" not in str(v)
        and "Número" not in str(v)
    ])

    disc_np_map = {}  # {disciplina: col_np}
    for idx, dc in enumerate(disc_cols):
        end = disc_cols[idx + 1] if idx + 1 < len(disc_cols) else len(np_row)
        disc_name = canonizar_disciplina(str(disc_row[dc]).strip())
        for c in range(dc, min(end, len(np_row))):
            if np_row[c] and str(np_row[c]).strip() == "NP.":
                # Se já existe uma coluna NP para esta disciplina (ex.: duas
                # grafias diferentes da mesma cadeira na mesma pauta), não
                # substituir — manter a primeira encontrada.
                disc_np_map.setdefault(disc_name, c)
                break

    # Ler linhas de dados (a partir de header_idx + 2)
    registos = []
    turma_atual = None

    for row in rows[header_idx + 2:]:
        # Actualizar turma se col 0 tem valor
        if row[0] and str(row[0]).strip():
            turma_atual = extrair_turma(row[0])

        # Nome do aluno está na col 7
        nome_val = row[7] if len(row) > 7 else None
        if not nome_val or not str(nome_val).strip():
            continue

        nome_aluno = str(nome_val).strip()

        # Extrair nota NP por disciplina
        for disc, col_np in disc_np_map.items():
            nota = parse_nota(row[col_np] if col_np < len(row) else None)
            registos.append({
                "turma":       turma_atual,
                "nome_aluno":  nome_aluno,
                "disciplina":  disc,
                "nota":        nota,
                "semestre":    SEMESTRE,
            })

    return registos

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    # Determinar ficheiros a processar
    if len(sys.argv) > 1:
        ficheiros = sys.argv[1:]
    else:
        pasta = os.path.join(os.path.dirname(__file__), "notas")
        ficheiros = glob.glob(os.path.join(pasta, "*.xlsx"))
        if not ficheiros:
            print("Coloque os ficheiros .xlsx na pasta 'notas/' ou passe-os como argumento.")
            print("Uso: python importar_notas.py ficheiro1.xlsx ...")
            sys.exit(1)

    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")

    # Construir cache de alunos: {(normalizar(nome), turma): aluno_id}
    alunos_cache = {}
    for a in db.execute("SELECT id, nome, turma FROM alunos WHERE ano_letivo=?", (ANO_LETIVO,)).fetchall():
        alunos_cache[(normalizar(a["nome"]), a["turma"])] = a["id"]
    # Cache secundário só por nome (para casos onde turma pode divergir ligeiramente)
    alunos_por_nome = {}
    for (n, t), aid in alunos_cache.items():
        if n not in alunos_por_nome:
            alunos_por_nome[n] = []
        alunos_por_nome[n].append((t, aid))

    total_notas  = 0
    total_novos  = 0
    nao_encontrados = set()
    disciplinas_vistas = set()

    for path in sorted(ficheiros):
        print(f"\nA processar: {os.path.basename(path)}")
        registos = parse_ficheiro(path)
        print(f"  {len(registos)} registos extraídos")
        disciplinas_vistas.update(r["disciplina"] for r in registos)

        for r in registos:
            nome_n = normalizar(r["nome_aluno"])
            turma  = r["turma"]

            # Procurar por nome + turma exacta
            aluno_id = alunos_cache.get((nome_n, turma))

            # Fallback: só por nome (quando turma não coincide 100%)
            if aluno_id is None and nome_n in alunos_por_nome:
                candidatos = alunos_por_nome[nome_n]
                if len(candidatos) == 1:
                    aluno_id = candidatos[0][1]
                else:
                    # Tentar turma parcial (ex: '12A1 CT' vs '12A1 CT ')
                    for ct, cid in candidatos:
                        if turma and ct and normalizar(ct) in normalizar(turma):
                            aluno_id = cid
                            break

            if aluno_id is None:
                nao_encontrados.add(f"{r['nome_aluno']} ({turma})")
                continue

            # Só inserir se nota não for None
            if r["nota"] is None:
                continue

            existing = db.execute(
                "SELECT id FROM notas WHERE aluno_id=? AND disciplina=? AND periodo=?",
                (aluno_id, r["disciplina"], r["semestre"])
            ).fetchone()

            if existing:
                db.execute(
                    "UPDATE notas SET nota=? WHERE id=?",
                    (r["nota"], existing["id"])
                )
            else:
                db.execute(
                    "INSERT INTO notas (aluno_id, disciplina, periodo, nota) VALUES (?,?,?,?)",
                    (aluno_id, r["disciplina"], r["semestre"], r["nota"])
                )
                total_novos += 1

            total_notas += 1

    db.commit()
    db.close()

    print(f"\n{'='*50}")
    print(f"✓ {total_notas} notas processadas  ({total_novos} novas inserções)")

    print(f"\nDisciplinas encontradas nas pautas ({len(disciplinas_vistas)}):")
    for d in sorted(disciplinas_vistas):
        marca = "" if d in DISCIPLINAS_ALIAS.values() or len(d) > 6 else "  ← grafia abreviada/pouco usual? confirmar se corresponde a uma disciplina já existente"
        print(f"   - {d}{marca}")
    print("   (Se aqui aparecerem duas entradas para a mesma disciplina com nomes")
    print("    diferentes — ex. 'Econ C' e 'ECO. C' — adicionar a variante a")
    print("    DISCIPLINAS_ALIAS no topo deste script e voltar a importar.)")

    if nao_encontrados:
        print(f"\n⚠  {len(nao_encontrados)} aluno(s) não encontrado(s) na BD:")
        for n in sorted(nao_encontrados)[:20]:
            print(f"   - {n}")
        if len(nao_encontrados) > 20:
            print(f"   ... e mais {len(nao_encontrados)-20}")
        print("\n→ Certifique-se de que importou primeiro os alunos (python importar_alunos.py)")

if __name__ == "__main__":
    main()
