---
name: render-regiao-oregon-migracao-adiada
description: O portal no Render está na região Oregon (EUA); migração para Frankfurt (e/ou Azure) foi discutida e adiada pelo utilizador
metadata:
  node_type: memory
  type: project
  originSessionId: 00c75f05-c415-45cd-a1c8-31658c85db17
  modified: 2026-11-02T12:47:31.893Z
---

O serviço `portal-avaliacao` no Render está na região **Oregon (EUA)**, confirmado pelo utilizador em 2026-11. Contém dados pessoais de alunos menores (RGPD), por isso a região europeia (Frankfurt) é desejável. O utilizador decidiu **deixar isto para já**, mas quer poder retomá-lo.

**Why:** o Render não permite mudar a região de um serviço existente; é preciso criar um serviço novo e copiar o disco `/data` (`portal.db`, `fotos/`, `slides/`). O portal não tem páginas de exportar/restaurar cópia de segurança, e a Web Shell do Render não permite tirar ficheiros.

**How to apply:** se o utilizador voltar ao tema, propor (1) construir páginas admin «Exportar cópia de segurança» (zip com BD via sqlite backup + fotos + slides) e «Restaurar cópia»; (2) acrescentar `region: frankfurt` ao `render.yaml`; (3) criar serviço novo em Frankfurt com disco `db` em `/data`, `DATABASE=/data/portal.db`, nova `SECRET_KEY`; (4) janela sem alterações durante a cópia; (5) testar e só depois suspender/apagar o de Oregon (o endereço pode mudar, avisar PT e professores). Juntar com a migração para Azure, também adiada (ver [[projeto-portal-avaliacao-contexto]]).
