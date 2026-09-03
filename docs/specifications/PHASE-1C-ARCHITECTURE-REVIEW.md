# Phase 1C — Domain Layer & Repository Adapters (Architecture Review)

**Status:** Reviewed
**Date:** 2026-09-03
**Reviewer:** Senior Architect

## 1. Documentos Analisados

1. `docs/SDD.md` (v1.1.0)
2. `docs/adr/ADR-001-Runtime-Language.md`
3. `docs/adr/ADR-002-Persistence-Strategy.md`
4. `docs/adr/ADR-003-Runtime-and-Queue-Strategy.md`
5. `docs/specifications/DATABASE-SPECIFICATION.md`
6. `docs/specifications/DATABASE-IMPLEMENTATION-PLAN.md`
7. `implementation_plan.md` (Artifact anterior)

---

## 2. Resumo Executivo

O plano de implementação da Fase 1C mapeia satisfatoriamente as diretrizes da Arquitetura Hexagonal (separação estrita entre Domain, Application e Infrastructure) em grande parte dos seus tópicos. A estrutura de pacotes está correta e a delegação da persistência aos adaptadores (SQLAlchemy Repository Adapters e Mappers) está alinhada aos ADRs 001 e 002.

Entretanto, o plano apresenta lacunas arquiteturais críticas que impedem o cumprimento de invariantes obrigatórias (como o controle de limites transacionais e atomicidade exigida pelo ADR-002 e ADR-003). Além disso, não define claramente os Aggregate Roots, o que pode causar proliferação indevida de repositórios. Devido a esses fatores, o plano requer revisões obrigatórias antes da implementação do código.

---

## 3. Matriz de Consistência com ADRs

| Invariante/decisão | Phase 1C preserva? | Evidência (Plano) | Finding |
| ------------------ | ------------------ | ----------------- | ------- |
| CAS exclusive transition guard | Sim | Citado indiretamente nos repositórios. | MEDIUM (Deve ser explícito nos Ports) |
| Audit append-only | Sim | Repositórios assíncronos lidam com a entidade e aprovações. | MEDIUM (Falta garantir atomicidade no plano) |
| Soft-delete | Sim | Mencionou a criação de Mappers bidirecionais. | INFO |
| Real foreign keys | N/A | Implementado no nível do banco (Fase 1B). | INFO |
| Immutable PublicationAttempt | Sim | Definido no modelo de Domínio. | INFO |
| Transactional Outbox | **Não estruturalmente** | Falta mecanismo para compartilhar transação entre Repositório e Outbox. | **BLOCKER** |
| Primitive IDs no payload | Sim (implícito) | Uso de IDs no Use Case. | INFO |
| At-least-once semantics | Sim | IngestArticleUseCase cuida de idempotência. | INFO |
| Domínio sem infraestrutura | Sim | Explicitamente declarado no Verification Plan. | INFO |

---

## 4. Pydantic — Análise Arquitetural Obrigatória

O plano questiona o uso do framework `Pydantic` v2 para a modelagem das entidades de Domínio.

**Análise:**
O ADR-001 selecionou Python explicitamente devido à força do `Pydantic` para sanitização e validação de "untrusted inputs" na borda do sistema (Zero-Trust Boundary). No entanto, de acordo com o Princípio de Independência de Frameworks da Arquitetura Hexagonal (SDD §7, §9), o "Core" do Domínio não deve ter dependências acopladas a frameworks externos, na medida do possível.

Transformar Entidades de Domínio puras em subclasses de `pydantic.BaseModel` polui o domínio com métodos de infraestrutura do framework (como `.model_dump()`, validações acopladas ao schema web, etc.). O `Pydantic` deve ser a barreira de proteção nos DTOs (Data Transfer Objects) da camada de **Application** ou dos **Controllers/Webhooks**.

**Decisão:** **REJECT** para Domain Entities. **APPROVE WITH CONSTRAINTS** para Application Layer.
- As **Domain Entities** devem ser modeladas usando bibliotecas nativas e puras, preferencialmente `dataclasses` (com `slots=True` e `kw_only=True` para performance e segurança).
- O **Pydantic** será utilizado rigorosamente na fronteira de entrada (Application DTOs, Schemas do Webhook e validações de payloads externos/LLMs).

---

## 5. Dependency Injection — Análise Arquitetural Obrigatória

O plano questiona o uso de frameworks de Injeção de Dependências (como `svcs` ou `punq`).

**Análise:**
O princípio de Injeção de Dependência (DI) é absolutamente obrigatório na Arquitetura Hexagonal: os Casos de Uso devem receber as instâncias dos *Ports* (Interfaces) via construtor, nunca instanciá-los diretamente.
Entretanto, a introdução de um framework ou container de DI de terceiros adiciona complexidade operacional precoce ao MVP, quebrando o direcionamento de "Operational Simplicity" do ADR-002 e ADR-003. A resolução de dependências pode e deve ser feita manualmente (Constructor Injection) através de uma *Composition Root* (ex: funções de dependência no FastAPI, ou um módulo factory).

**Decisão:** **REJECT** (Containers/Frameworks) / **APPROVE** (Princípio DI manual).
- Implementar DI através da injeção explícita de dependências nos construtores (`__init__`) dos Use Cases. Não adicionar libs de container DI por enquanto.

---

## 6. Análise das Entidades de Domínio

O plano propõe: `Article`, `EditorialBrief`, `ContentVersion`, `ValidationResult`, `ApprovalDecision`, `PublicationAttempt`.

**Análise:**
As entidades estão corretas semanticamente, mas carecem de distinção tática de *Domain-Driven Design (DDD)* (Aggregate Roots vs. Value Objects/Local Entities).
- `Article`: **Aggregate Root**.
- `ContentVersion`: **Aggregate Root** (tem seu próprio ciclo de vida, CAS e interações complexas de workflow, como as aprovações e tentativas de publicação).
- `EditorialBrief`: Dependendo da modelagem, pode pertencer ao Aggregate do `Article`.
- `ValidationResult`, `ApprovalDecision`, `PublicationAttempt`: Devem ser tratadas como **Entities/Value Objects aninhados** sob o Aggregate Root de `ContentVersion`. Eles não devem possuir Repositórios próprios; devem ser manipulados através do `ContentVersionRepository`.

---

## 7. Análise dos Repository Ports

Os Ports definidos (`ArticleRepository`, `ContentVersionRepository`, `EditorialBriefRepository`) estão coerentes, desde que retornem as Entidades de Domínio (ex: `Article`) e não exponham objetos do SQLAlchemy.

**Análise:**
Para suportar o *CAS* (Compare-and-Swap) e garantir que o domínio permaneça puro:
- O método de transição de estado não pode receber `AsyncSession`.
- Deve existir um método explícito nos Ports, por exemplo, `transition_state(version: ContentVersion, expected_state: Status) -> None`, que será implementado no adaptador concreto para disparar o CAS SQL.

---

## 8. Análise dos Repository Adapters & 9. Mappers

**Análise:**
O fluxo `Domain Port -> Adapter -> SQLAlchemy Model -> PostgreSQL` com mappings bidirecionais (em `mappers.py`) está correto e validado.
- Os *Mappers* evitam o vazamento de metadados do SQLAlchemy (como estado de tracking, `_sa_instance_state`) para o domínio.
- Os Adaptadores devem capturar e traduzir exceções de infraestrutura (como `IntegrityError` no PostgreSQL) para Exceções de Domínio (ex: `DuplicateArticleError`).

---

## 10. Análise dos Use Cases

- **`IngestArticleUseCase`**: Correto. Deve cuidar do mapeamento e tratamento do erro de concorrência (idempotência).
- **`UpdateVersionStatusUseCase`**: Deve orquestrar a aprovação.
- *Porém*, falta clareza sobre como garantir que a transição de estado, as inserções de auditoria e a emissão do Outbox ocorram **na mesma transação**. (Vide Item 11).

---

## 11. Transaction Boundaries (O BLOCKER)

**Problema:** O ADR-002 Invariant 1 (Atomic State Transition Unit) e o ADR-003 (Transactional Outbox) exigem que a transição de estado no Repositório, a escrita no Audit Trail e o Inserte no Outbox ocorram em um único bloco `BEGIN ... COMMIT`.

Se a camada de Application orquestra múltiplos Repositórios (ex: `ContentVersionRepository` e `OutboxRepository`), não há no plano nenhum mecanismo (ex: `UnitOfWork`) para gerenciar essa fronteira transacional sem vazar a `AsyncSession` do SQLAlchemy para o Use Case (o que violaria a arquitetura hexagonal).

**Finding:** É obrigatório definir um padrão de Unidade de Trabalho (Unit of Work - UoW) que atue como Port na camada de Domínio/Aplicação e que tenha uma implementação concreta baseada em `AsyncSession` na camada de Infraestrutura, permitindo transações atômicas seguras em múltiplos repositórios.

---

## 12. Test Strategy

O Verification Plan é satisfatório (Unit test no Domínio, Integration no Repo com PostgreSQL via testcontainers, mocks na camada Application).
- **Adicional Requerido:** Devem ser adicionados testes de integração específicos para o `UnitOfWork`, garantindo que um `rollback` cancele atomicamente uma alteração no Aggregate e o Evento no Outbox simultaneamente.

---

## 13. Findings Classificados

| ID | Nível | Localização | Problema / Justificativa | Solução | Exige alteração no plano? |
|----|-------|-------------|--------------------------|---------|---------------------------|
| F1 | **BLOCKER** | Architecture (Transactions) | Ausência de mecanismo de compartilhamento transacional (UoW) entre múltiplos repositórios (violando Invariant 1 e ADR-003). | Adicionar o padrão `UnitOfWork` (Port no domínio, Adapter na infraestrutura) no Plano de Implementação. | Sim |
| F2 | **HIGH** | Domain Entities | O uso do framework `Pydantic` contamina a pureza das entidades de Domínio conforme Arquitetura Hexagonal. | Restringir `Pydantic` a DTOs/Webhooks. Utilizar `dataclasses` para entidades puras no Domínio. | Sim |
| F3 | **MEDIUM** | DDD / Ports | Não há clareza de Aggregate Roots. O risco é criar repositórios para sub-entidades (como `PublicationAttempt`), ferindo as fronteiras de transação de domínio. | Restringir interfaces de repositórios aos Aggregate Roots (`Article`, `ContentVersion`). Outras entidades são persistidas em cascata pelo repositório principal. | Sim |
| F4 | **LOW** | Dependency Injection | Framework de DI desnecessário. | Usar Constructor Injection pura. | Não |

---

## 14. Decision sobre as Open Questions

1. **Pydantic**: **REJECT** para Domain Entities puras. **APPROVE WITH CONSTRAINTS** para Application Layer (DTOs e Boundaries).
2. **Dependency Injection**: **REJECT** o uso de container/framework de DI (svcs/punq). **APPROVE** o princípio de Dependency Injection usando injeção de dependência nativa por construtor.

---

## 15. Verdict Final

**READY WITH REQUIRED REVISIONS**

O plano de implementação está **arquiteturalmente bloqueado (F1 e F2)**.

O agente de implementação não pode iniciar a codificação antes que o documento `implementation_plan.md` seja revisado para acomodar:
1. O padrão `UnitOfWork` (UoW) nas interfaces e adaptadores.
2. A formalização do uso de `dataclasses` para Entidades Puras.
3. A formalização de que apenas Aggregate Roots possuirão Repositórios dedicados.

Após a correção documental na branch atual, o plano estará pronto para prosseguir à implementação pela equipe competente.
