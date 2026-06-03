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
        disc_name = str(disc_row[dc]).strip()
        for c in range(dc, min(end, len(np_row))):
            if np_row[c] and str(np_row[c]).strip() == "NP.":
                disc_np_map[disc_name] = c
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

    for path in sorted(ficheiros):
        print(f"\nA processar: {os.path.basename(path)}")
        registos = parse_ficheiro(path)
        print(f"  {len(registos)} registos extraídos")

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

    if nao_encontrados:
        print(f"\n⚠  {len(nao_encontrados)} aluno(s) não encontrado(s) na BD:")
        for n in sorted(nao_encontrados)[:20]:
            print(f"   - {n}")
        if len(nao_encontrados) > 20:
            print(f"   ... e mais {len(nao_encontrados)-20}")
        print("\n→ Certifique-se de que importou primeiro os alunos (python importar_alunos.py)")

if __name__ == "__main__":
    main()
