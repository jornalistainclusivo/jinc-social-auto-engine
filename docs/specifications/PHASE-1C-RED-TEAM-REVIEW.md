# Phase 1C — Domain Layer & Repository Adapters (Red Team Review)

**Status:** Reviewed
**Date:** 2026-09-03
**Reviewer:** Red Team

## 1. Documentos Analisados
1. `implementation_plan.md` (revisado)
2. `docs/specifications/PHASE-1C-ARCHITECTURE-REVIEW.md`
3. `docs/SDD.md` (v1.1.0)
4. `docs/adr/ADR-001-Runtime-Language.md`
5. `docs/adr/ADR-002-Persistence-Strategy.md`
6. `docs/adr/ADR-003-Runtime-and-Queue-Strategy.md`
7. `docs/specifications/DATABASE-SPECIFICATION.md`

---

## 2. Ataques Realizados

Os seguintes vetores de ataque arquitetural foram explorados:
- **Ataque ao CAS (Compare-And-Swap):** Validação da persistência de um Aggregate Root após transição de estado na memória.
- **Ataque a Aggregate Roots (Nested Collections):** Exploração das falhas de mapeamento reverso (Domain -> SQLAlchemy) em entidades aninhadas.
- **Ataque ao Isolamento de AsyncSession:** Exploração do risco de commit prematuro pelo adaptador de repositório.
- **Ataque à Atomicidade e ao Outbox:** Simulação de inserção no Outbox e posterior falha de banco.

---

## 3. Cenários de Falha Considerados

- **Cenário A (Commit):** State transition + audit + outbox. Se tudo correr bem, persistem. (Aprovado no plano).
- **Cenário B (Rollback):** Falha antes do fim da transação. O UoW dá rollback. (Aprovado no plano).
- **Cenário C (CAS Update):** Como a entidade modificada em memória é traduzida para uma cláusula SQL `WHERE expected_version`? (Falha encontrada - Impedance Mismatch).
- **Cenário D (Repositório comitando inadvertidamente):** O adaptador recebe a sessão e executa `await self.session.commit()`. (Falha encontrada - Quebra de encapsulamento do UoW).

---

## 4. Análise do UnitOfWork
O `UnitOfWork` gerencia as transações, mas ao expor a `AsyncSession` diretamente aos Repositórios sem proteções explícitas (ex: `autocommit=False` rígido ou wrapping da sessão), abre a possibilidade de os adaptadores cometerem hijack da transação. **(Finding F3)**.

## 5. Análise do isolamento de AsyncSession
O isolamento no Port é satisfatório, pois `AsyncSession` nunca atravessa a fronteira. Contudo, internamente na camada de Infraestrutura, a passagem de `AsyncSession` exige cautela redobrada.

## 6. Análise de Atomicidade
A atomicidade macroestatal está garantida pelo bloco `async with uow:`. Se houver falhas de processamento, o `__aexit__` com `exc_type` dá trigger no rollback.

## 7. Análise do Outbox
O Outbox divide a sessão com os Repositórios via `uow.outbox`. O isolamento e a atomicidade transacional estão teoricamente corretos, desde que os Repositórios não disparem flushes ou commits independentes.

## 8. Análise do CAS (Compare-And-Swap)
**Crítico:** O plano diz que as entidades (dataclasses) são alteradas no domínio e salvas via Repositório, mas prescreve CAS. No ecossistema SQLAlchemy, usar `session.merge()` em uma dataclass modificada disparará um `UPDATE` comum, sem o critério de concorrência (`WHERE status='PENDING'`). O CAS precisa ser operado a nível de Query, o que entra em conflito com o salvamento de uma dataclass inteira. **(Finding F1)**.

## 9. Análise dos Aggregate Roots
As raízes (`Article`, `ContentVersion`) estão bem definidas. Mas a persistência de coleções aninhadas (ex: `ApprovalDecision` dentro de `ContentVersion`) via mappers bidirecionais tende a causar ciclos destrutivos (DELETE/INSERT cascata) no SQLAlchemy se a identidade primária não for controlada perfeitamente na dataclass. **(Finding F2)**.

## 10. Análise dos Repository Ports
Granularidade restrita aos Aggregate Roots é correta. 

## 11. Análise dos Mappers
Os mappers não lidaram explicitamente com a complexidade de reconstrução de coleções aninhadas e CAS. 

## 12. Análise de Pydantic
Proteção correta: excluído das Domain Entities.

## 13. Análise de Dependency Injection
O *Constructor Injection* via Composition Root blinda o Domínio adequadamente sem introduzir complexidade precoce.

## 14. Análise dos Use Cases
Bem definidos, orquestrando corretamente os boundaries transacionais via UoW. 

## 15. Análise dos Testes
Os testes estão bem planejados, mas falta especificar um teste de integração que force uma *Race Condition* durante o CAS para provar a consistência do sistema e o lançamento da `ConcurrentModificationError`.

---

## 16. Findings Classificados

| ID | Nível | Localização | Cenário de Ataque / Justificativa | Invariante Afetado | Recomendação | Bloqueia? |
|----|-------|-------------|-----------------------------------|--------------------|--------------|-----------|
| F1 | **CRITICAL** | Repositories / Mappers | *CAS Impedance Mismatch*: O Use Case altera a dataclass em memória. O Repositório faz `session.merge()`. O CAS (`WHERE expected_version`) é ignorado e sobrescrito silenciosamente, causando race conditions. | ADR-002 Invariant 1 (CAS) | O contrato do Repositório deve expor métodos específicos para CAS (ex: `transition_state(version_id, expected_status, new_status)`) que executem `update()` a nível de banco, ao invés de usar `merge()` indiscriminado nas dataclasses. | SIM |
| F2 | **HIGH** | Aggregate Roots / Mappers | *Nested Collections Destructive Updates*: Ao mapear as sub-entidades de `ContentVersion` de volta para SQLAlchemy models sem controle estrito de PKs/Identity, o ORM pode executar deletes/inserts indevidos. | Data Integrity / Audit Trail | O Mapper deve definir estritamente o tratamento de coleções (preferencialmente operações append-only no banco para entidades como auditoria e publicação, sem cascades destrutivos). | SIM |
| F3 | **MEDIUM** | UnitOfWork Adapter | *Accidental Transaction Hijack*: Um desenvolvedor chama `self.session.commit()` acidentalmente num Repositório, quebrando o UoW. | Atomicidade do Outbox | Definir salvaguardas (wrapping da sessão ou restrições severas de linting) para impedir commits fora do `UoW.__aexit__`. | NÃO |

---

## 17. Verdict Final

**HOLDS WITH MATERIAL REVISIONS**

O plano possui lacunas mecânicas profundas na relação entre os Mappers do SQLAlchemy e a exigência de CAS/concorrência. Tentar persistir Aggregate Roots massivos (com coleções aninhadas) usando `dataclasses` exigirá estratégias de mapeamento que não foram previstas no plano e que potencialmente violarão a segurança exigida. A equipe de planejamento deve endereçar os findings F1 e F2 explicitamente antes de gerar código.
