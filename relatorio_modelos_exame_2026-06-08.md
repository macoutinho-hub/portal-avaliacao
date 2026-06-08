# Preparação e validação de modelos de "nota esperada de exame" — AVAL_CPA.xlsx

Data: 2026-06-08

## 1. Origem e limpeza dos dados

Ficheiro de origem: `AVAL_CPA.xlsx`, folha "Registos Biográficos Disciplina" — 153.726 linhas, 14 anos lectivos (2010/2011 a 2023/2024), 3.373 alunos, 80 disciplinas.

Foram excluídas 116 linhas anómalas (registos sem nº de aluno, com todos os valores desalinhados uma coluna para a direita — erro de exportação, não recuperável com confiança).

## 2. Normalização das notas de exame (CE1/CE2)

As notas de exame não usam uma escala única. Foi confirmada empiricamente a seguinte correspondência, e todas as notas foram convertidas para a escala 0-20:

| Nível / ano | Escala original | Observação |
|---|---|---|
| 4º ano, em 2012/2013 | 1-5 | escala qualitativa, mudou no ano seguinte |
| 4º ano, a partir de 2013/2014 | 0-100 | |
| 6º ano | 0-100 | consistente em todos os anos |
| 9º ano | 0-100 | consistente em todos os anos |
| Secundário (10º-12º) | 0-200 | consistente em todos os anos |

Esta mudança de escala no 4º ano entre 2012/2013 e 2013/2014 é um exemplo real do tipo de "regime change" que tínhamos discutido como risco para um modelo treinado sobre vários anos — tratá-la correctamente (por ano, não só por nível) era essencial para não enviesar os resultados.

Notou-se ainda que os anos 2019/2020 a 2021/2022 têm muito poucos exames registados no secundário (provavelmente relacionado com a pandemia — exames cancelados ou com regras excepcionais nesses anos). Foram marcados com a flag `epoca_atipica` e excluídos do treino/validação dos modelos (mas mantidos nos CSVs, para decisão futura).

## 3. Segmentação

Em vez de um único modelo, os dados de exame foram divididos em dois grupos estruturalmente distintos, tal como recomendado:

- **`ciclo`** — Provas finais de ciclo (4º, 6º, 9º anos): 3.331 observações válidas
- **`secundario`** — Exames nacionais do secundário (10º-12º): 2.393 observações válidas

## 4. Modelos treinados (protótipo)

Para cada grupo, foi treinado um modelo de regressão linear (OLS) com 4 variáveis, todas calculadas a partir do contexto da própria observação (sem usar a nota de exame de outros para "prever" a do próprio aluno de forma circular):

- x1 — média das notas periódicas internas do aluno nessa disciplina/ano
- x2 — CIF (classificação interna final) do aluno nessa disciplina/ano
- x3 — média de exame da turma, nessa disciplina/ano (excluindo a própria observação)
- x4 — média de exame do nível/ano de escolaridade, nessa disciplina/ano (contexto mais amplo)

Validação por divisão treino/teste (80/20):

| Grupo | Observações | R² (treino) | R² (teste) | MAE (teste, em 0-20) | Desvio dos resíduos |
|---|---|---|---|---|---|
| ciclo | 3.318 | 0,66 | 0,62 | 2,15 | 3,03 |
| secundário | 2.209 | 0,64 | 0,69 | 1,66 | 2,11 |

**Leitura dos resultados:**

- Em ambos os grupos, o desempenho no teste é consistente com o do treino — não há sinais de sobreajuste (overfitting). Isto é uma boa indicação de que o modelo capta um padrão real, generalizável, e não está apenas a "decorar" os dados de treino.
- Um R² à volta de 0,6-0,7 significa que o modelo explica cerca de 60-70% da variação das notas de exame a partir do histórico interno do aluno e do contexto — o que é um resultado razoável para este tipo de previsão. Os restantes 30-40% reflectem, como discutido, factores que os dados internos não conseguem captar (desempenho no dia do exame, preparação externa, dificuldade da prova nesse ano, etc.).
- O erro médio absoluto (MAE) ronda os 1,7-2,2 valores (em 20) — ou seja, em média, a previsão erra por essa margem. É um valor que parece razoável para sinalizar desvios anómalos (outliers), mas não suficiente para "adivinhar" a nota exacta de exame.
- O grupo "secundário" tem um ajuste ligeiramente melhor do que o "ciclo" — possivelmente porque a CIF e as médias periódicas no secundário estão mais próximas, em significado, da prova de exame nacional.

## 5. Ficheiros produzidos

- `notas_internas.csv` — notas periódicas + CIF/CFD, limpas (152.000 observações)
- `exames_ciclo_basico.csv` — exames de ciclo (4º/6º/9º), normalizados para 0-20, com metadados de escala original e época atípica
- `exames_secundario.csv` — exames nacionais do secundário, normalizados para 0-20, com os mesmos metadados
- `preparar_dados_aval.py` — script de limpeza/normalização/segmentação (reprodutível)
- `treinar_modelos_exame.py` — script de treino e validação dos modelos (protótipo)

## 6. Próximos passos sugeridos

1. Decidir o que fazer com os anos atípicos da pandemia (incluir, excluir, ou tratar à parte).
2. Considerar acrescentar uma referência externa — médias nacionais do exame por disciplina/ano — como variável adicional, para corrigir variações de dificuldade da prova entre épocas (continua a ser a maior lacuna identificada).
3. Integrar esta lógica em `analytics.py`, seguindo o mesmo padrão de cache/circularidade já usado no modelo de notas internas, para que apareça no portal lado a lado com a "Nota Esperada vs. Nota Real".
