# Phase 1C Reconciliation

## Executive Summary
Este documento estabelece as decisões de reconciliação para endereçar os findings de nível CRITICAL e HIGH apontados pela revisão do Red Team (Phase 1C). O plano original foi alterado para formalizar os contratos arquiteturais, especificamente em concorrência, mapeamento e ciclo de vida de transações.

## Red Team Findings

### F1 — CAS Impedance Mismatch
**Severity:** CRITICAL
**Red Team Argument:** Alterar a dataclass e usar `session.merge()` não impõe CAS no banco, permitindo sobrescrita silenciosa de modificações concorrentes.
**Architectural Impact:** Ocorrência de Race Conditions severas e violação da Invariante de CAS (ADR-002).
**Decision:** Adoção de Targeted Persistence e proibição de `session.merge()` para aggregate roots sujeitos a CAS.
**Rationale:** Em vez de "mesclar" o grafo modificado de Dataclass para ORM confiando no Identity Map, o repositório possuirá métodos de intenção `transition_status(aggregate_id, expected_version, new_state)` que constroem uma cláusula `UPDATE ... WHERE ... AND version = ?`. Se `affected_rows == 0`, lança-se `ConcurrentModificationError`.
**Implementation Consequence:** Proibição de métodos CRUD genéricos como `save(entity)`. O port reflete os Casos de Uso. 
**Test Requirement:** CAS concurrency test provando a invalidação do T2.
**Status:** Resolved (Documented in Plan).

### F2 — Nested Collections Destructive Updates
**Severity:** HIGH
**Red Team Argument:** Substituir e mesclar coleções aninhadas como listagens de `PublicationAttempt` pode engatilhar DELETEs indesejados devido a políticas SQLAlchemy e ciclos bidirecionais ingênuos. 
**Architectural Impact:** Perda irreversível de histórico (Audit Trails) na persistência de Aggregates.
**Decision:** Adoção de Estratégias Append-Only para o histórico da versão.
**Rationale:** As coleções temporais não representam "estado atual mutável", mas logs inseridos (append-only).
**Implementation Consequence:** Os mappers desativarão deletes (ex: removerão o cascade destrutivo explícito) nessas dependências, e os Repositórios ganharão assinaturas `append_publication_attempt`. Um INSERT simples é disparado.
**Test Requirement:** Append-only test garantindo que insert não sobrescreve os dados.
**Status:** Resolved (Documented in Plan).

### F3 — Accidental Transaction Hijack
**Severity:** MEDIUM
**Red Team Argument:** Abstração de UoW na porta Application vs. Instâncias abertas de AsyncSession nos Repositórios permitem que Repositórios emitam `session.commit()` ou `session.rollback()` individualmente.
**Architectural Impact:** Quebra das garantias macroestatais definidas pelo UoW, separando transições do Outbox.
**Decision:** Restrição do *Transaction Ownership* ao `UnitOfWork` puramente.
**Rationale:** Adapters que persistem os dados jamais poderão manipular o fluxo principal do banco para além do Statement/Query level. A transação da aplicação existe unicamente na orquestração da Application Layer via UoW Context Manager.
**Implementation Consequence:** Nenhuma chamada a `.commit()` residirá fora da classe do UoWAdapter (em seu respectivo `__aexit__`). AsyncSession é ocultado do Domain. 
**Test Requirement:** Teste isolado e revisão estática bloqueando uso isolado do hijack.
**Status:** Resolved (Documented in Plan).

## Decisions
- **CAS operations** são modeladas em queries específicas.
- **Append-only collections** são inseridas através de seus próprios métodos em repositórios de suas respectivas Aggregate Roots.
- **`session.merge()`** está expressamente proibido para as raízes da aplicação (ContentVersion).
- O **UnitOfWork** detém controle unilateral de `commit/rollback`.
- Nenhuma dependência Pydantic será importada pelo Domínio.

## Revised Contracts
Os repositórios representam intenções operacionais focadas (ex: `load()`, `transition_status()`, `append_audit()`).

## Revised Mapper Strategy
A conversão Bidirecional `ORM <-> Domain` existirá primordialmente para leitura (Read -> Dataclasses). Na gravação (Update), o update é seletivo aos campos (Targeted Persistence) e a coleções que requerem inserções nominais, ignorando mesclagens amplas.

## Revised UnitOfWork Strategy
Atua isoladamente na orquestração:
```python
async with uow:
    # Ler
    # Aplicar regra
    # Invocar targeted methods do repo 
    # Adicionar na Fila / Outbox
# commit via __aexit__
```

## Identity Map Strategy
Para evitar dados obsoletos, o fluxo é estrito: "Carrega -> Transforma -> Comando Direcionado". Como não haverá atualizações usando instâncias pré-modificadas do ORM, o Identity Map tem chance nula de cometer equívocos com objetos órfãos, e os flushes não comprometerão invariantes de domínio.

## Append-Only Strategy
Novos registros em coleções críticas (Auditorias, Decisões de Aprovação, Tentativas de Publicação) serão introduzidos isoladamente através de INSERTS.

## Testing Requirements
Implementar formalmente (como testes de produção):
- **CAS concurrency test**
- **Atomicity test**
- **Append-only test**
- **Transaction hijack test**
- **Identity Map / mapper test**

## Remaining Risks
Nenhum risco arquitetural material resta no que tange os findings abertos de concorrência e transações.  A equipe agora conta com especificações restritivas que protegem o mecanismo contra corrupção dos dados de negócio.

## Deferred Decisions
Eventuais ajustes na otimização de `SELECT N+1` gerados pelo novo uso rigoroso do Mapeamento serão resolvidos no ciclo real de testes e perfilagem (Tuning) caso necessário, durante a Fase de Implementação (1C) sem mudar o modelo arquitetural.

## Final Verdict
**READY FOR DECISION READINESS**
