# Portal de Avaliação — Colégio Pedro Arrupe

Aplicação Flask (Python) para avaliação de alunos: notas, avaliação intercalar, Competências Transversais (CT), projeto, fichas e apresentação de turma. Interface e respostas em **português de Portugal**.

## Stack e ficheiros
- `app.py` (rotas e lógica, ficheiro grande), `competencias.py` (CT: níveis, momentos), `importar_*.py` (importações Excel/PDF), `templates/` (Jinja + Bootstrap).
- sqlite3 (`DATABASE` por variável de ambiente), openpyxl, pdfplumber, gunicorn.
- Produção: Render, região Oregon, disco em `/data` (`portal.db`, `fotos/`, `slides/`). `render.yaml` e `DEPLOY.md` descrevem o serviço.
- Deploy: o utilizador faz **Push origin** no GitHub Desktop e depois **Manual Deploy** no Render. Não fazer push sem ele pedir.

## Perfis
- `admin`, `diretor` (= PT, professor titular de turma; identificado por `session["turma"]`, lista separada por vírgulas) e `professor`.
- Atribuições professor–turma–disciplina: tabela `prof_disc` (Admin → Atribuições). Decide o que cada professor vê nas CT.
- Matrícula por disciplina: `aluno_disciplina`. Alunos sem linhas contam como tendo todas as disciplinas.

## Convenções importantes
- Nomes de disciplinas variam entre pautas: normalizar com `canonizar_disciplina`, `_canon_disc_intercalar`, `_chave_disc`, `DISC_FAMILIAS`, `ABREVIATURAS`. Ao acrescentar uma disciplina nova, rever também `ORDEM_TODAS`/`_ORDEM`.
- 12.º ano: «História» = História A; «ING.» = coluna própria «Opção: Inglês» (Ing Op).
- «Hora de PT» e «PT» não têm avaliação de CT (`_CT_SEM_AVALIACAO`).
- CT: `_ct_atribuicoes`, `_ct_alunos` (inclui alunos de outras turmas do mesmo ano com a disciplina na lista), `_ct_grupos_orientador` (projeto).
- Reimportar matrículas ou pautas pode substituir edições feitas à mão no portal.

## Como testar
- Base temporária: definir `DATABASE` para um ficheiro novo e usar o cliente de testes Flask. Pode usar-se `/_dev/login` num servidor de desenvolvimento.
- **Nunca** usar dados reais de alunos em testes, capturas de ecrã ou documentos: usar dados fictícios.

## Dados pessoais (RGPD)
- Contém dados de alunos menores. `portal.db`, fotos e pautas não devem ser partilhados nem copiados para fora do colégio. Os ficheiros `.db`, `portal.db-journal` e `docs/` aparecem frequentemente como alterados: não os incluir em commits sem verificar.

## Decisões e pendentes
- Migração do Render para Frankfurt/Azure: adiada (ver `docs/memoria-claude/`). O Render não muda a região de um serviço; exige serviço novo e cópia do disco.
- Depois de cada deploy relevante: reimportar a pauta intercalar do 12.º (Ing Op, HIST. G, C. Pol) e a do 11.º (Mat G → A/B/MACS) se ainda não foi feito; eliminar a coluna «FJ» em Consolidar Disciplinas.
- Ideias por fazer: regra estrita HIST. G → História A na intercalar; atualizar `/ct/tutorial` para a divisão Professor/PT; remover avaliações CT antigas de «Hora de PT»; modo de projeto «só orientador»; páginas admin de cópia de segurança/restauro.
- Tutoriais para professores e PT estão em `docs/` e `Tutorial_CPA_Portal_CT.docx`.
