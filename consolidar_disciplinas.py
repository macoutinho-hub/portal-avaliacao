"""
Script para consolidar notas de disciplinas que foram importadas com nomes
diferentes mas correspondem à mesma disciplina (ex.: "ECO. C" e "Economia C",
"AI B" e "Aplicações Informáticas B").

Usa o mesmo mapa DISCIPLINAS_ALIAS de importar_notas.py para descobrir, em
cada tabela (notas e notas_finais), grupos de nomes que devem ser fundidos
num único nome canónico, e corrige os registos existentes.

Por omissão corre em modo SIMULAÇÃO (não escreve nada na BD) e mostra o que
seria alterado. Para aplicar as alterações:

    python consolidar_disciplinas.py --aplicar

Uso:
    python consolidar_disciplinas.py            # simulação (mostra o plano)
    python consolidar_disciplinas.py --aplicar  # aplica as alterações
"""

import sqlite3
import sys
import os

from importar_notas import normalizar, canonizar_disciplina, DISCIPLINAS_ALIAS

DATABASE = "portal.db"


def agrupar_por_canonico(nomes):
    """
    Recebe a lista de nomes de disciplina distintos encontrados na BD e
    devolve {nome_canonico: [nomes_originais...]} apenas para os grupos onde
    há mais do que um nome original a apontar para o mesmo canónico (i.e.
    onde há algo a consolidar).
    """
    grupos = {}
    for nome in nomes:
        canonico = canonizar_disciplina(nome)
        grupos.setdefault(canonico, []).append(nome)

    return {c: variantes for c, variantes in grupos.items() if len(variantes) > 1}


def consolidar_tabela(db, tabela, colunas_chave, aplicar):
    """
    colunas_chave: colunas (além de 'disciplina') que identificam um registo
    único — usadas para detetar conflitos ao renomear (ex.: aluno_id+periodo
    para 'notas', aluno_id+ano_letivo para 'notas_finais').
    """
    nomes = [r[0] for r in db.execute(f"SELECT DISTINCT disciplina FROM {tabela}").fetchall()]
    grupos = agrupar_por_canonico(nomes)

    if not grupos:
        print(f"  [{tabela}] nada a consolidar — todos os nomes já estão no formato canónico (ou são únicos).")
        return 0, 0

    total_atualizados = 0
    total_removidos = 0

    for canonico, variantes in sorted(grupos.items()):
        # Ignorar grupos onde o "canónico" não é, na prática, diferente de
        # nenhuma das variantes (ex.: duas grafias idênticas após normalizar
        # mas o canonizar devolveu uma delas tal-e-qual) — ainda assim vale a
        # pena reportar porque pode haver registos duplicados.
        outras = [v for v in variantes if v != canonico]
        if not outras:
            continue

        print(f"\n  [{tabela}] '{canonico}'  ←  {outras}")

        chave_sel = ", ".join(colunas_chave)
        for variante in outras:
            registos = db.execute(
                f"SELECT id, {chave_sel} FROM {tabela} WHERE disciplina=?",
                (variante,)
            ).fetchall()

            for reg in registos:
                filtro = " AND ".join(f"{c}=?" for c in colunas_chave)
                valores = tuple(reg[c] for c in colunas_chave)

                conflito = db.execute(
                    f"SELECT id FROM {tabela} WHERE disciplina=? AND {filtro}",
                    (canonico, *valores)
                ).fetchone()

                if conflito:
                    # Já existe um registo com o nome canónico para a mesma
                    # chave (aluno/período/ano) — não dá para só fazer
                    # UPDATE, porque criaria duplicados. Mantemos o registo
                    # canónico e removemos a variante (assumindo que o
                    # canónico é o mais recente/correto; reportamos para
                    # o utilizador poder verificar manualmente se for caso disso).
                    print(f"      conflito: já existe '{canonico}' para {dict(zip(colunas_chave, valores))}"
                          f" — a remover registo duplicado '{variante}' (id={reg['id']}, manter id={conflito['id']})")
                    if aplicar:
                        db.execute(f"DELETE FROM {tabela} WHERE id=?", (reg["id"],))
                    total_removidos += 1
                else:
                    if aplicar:
                        db.execute(f"UPDATE {tabela} SET disciplina=? WHERE id=?", (canonico, reg["id"]))
                    total_atualizados += 1

        if aplicar:
            print(f"      → renomeado(s) para '{canonico}'.")

    return total_atualizados, total_removidos


def main():
    aplicar = "--aplicar" in sys.argv[1:]

    if not os.path.exists(DATABASE):
        print(f"BD '{DATABASE}' não encontrada nesta pasta.")
        sys.exit(1)

    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")

    print("=" * 60)
    print("MODO: " + ("APLICAR ALTERAÇÕES" if aplicar else "SIMULAÇÃO (nada será escrito na BD)"))
    print("=" * 60)

    upd_notas, rem_notas = consolidar_tabela(db, "notas", ["aluno_id", "periodo"], aplicar)
    upd_finais, rem_finais = consolidar_tabela(db, "notas_finais", ["aluno_id", "ano_letivo"], aplicar)

    if aplicar:
        db.commit()

    db.close()

    print("\n" + "=" * 60)
    print("Resumo:")
    print(f"  notas:        {upd_notas} renomeada(s), {rem_notas} duplicada(s) removida(s)")
    print(f"  notas_finais: {upd_finais} renomeada(s), {rem_finais} duplicada(s) removida(s)")

    if not aplicar and (upd_notas or rem_notas or upd_finais or rem_finais):
        print("\n→ Isto foi uma simulação. Para aplicar de facto as alterações, corra:")
        print("    python consolidar_disciplinas.py --aplicar")
    elif not (upd_notas or rem_notas or upd_finais or rem_finais):
        print("\n✓ Não há nada a consolidar — os nomes de disciplinas já estão coerentes.")


if __name__ == "__main__":
    main()
