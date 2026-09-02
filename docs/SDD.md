---
jinc-sdd-version: 1.1.0
project-name: JincSAE (Jornalista Inclusivo Social Automation Engine)
project-context: backend
status: accepted
related-branch: docs/sdd-initial-architecture
tech-stack: [Undecided - Python / TypeScript candidates]
created-at: 2026-08-29
last-updated: 2026-08-30
authors: SDD Creator
---

# Software Design Document (SDD)

## 1. Document Status

* **Title:** Arquitetura do JincSAE (Jornalista Inclusivo Social Automation Engine)
* **Repository:** `jinc-social-engine`
* **Version:** 1.1.0
* **Status:** Accepted
* **Date:** 2026-08-30
* **Related Documents:** `docs/PRD.md`, `docs/ENGINEERING_CONSTITUTION.md`

---

## 2. Purpose

Este SDD define a arquitetura estrutural e lógica do **JincSAE**. Seu propósito é mapear os requisitos descritos no PRD e obedecer estritamente às restrições da Engineering Constitution, traduzindo-os em um design arquitetural com foco em confiabilidade editorial, modularidade e rastreabilidade.

Este documento **não** define implementações de infraestrutura final, frameworks exatos ou esquemas de banco de dados físicos (que serão objeto de ADRs subsequentes).

---

## 3. Scope

### In Scope

* Arquitetura lógica do motor de ingestão e processamento de artigos.
* Definição de limites e integrações com o WordPress, Provedores LLM e Redes Sociais.
* Modelagem conceitual do estado de aprovação e workflows de publicação.
* Padrões de validação rigorosos (Schema, Factual, Editorial, Acessibilidade).
* Estratégias de idempotência e regeneração de conteúdo.

### Out of Scope

* Interfaces de usuário (Front-end) detalhadas.
* Design final dos prompts de LLM.
* Configurações de infraestrutura (Terraform/Helm).
* Algoritmos internos de publicação automatizada sem intervenção humana (não permitido no MVP).

---

## 4. Architectural Drivers

A arquitetura do sistema é guiada pelos seguintes fatores críticos:

* **Confiabilidade Editorial:** Conteúdo gerado não deve inventar fatos ou alucinar.
* **Geração Probabilística vs. Estado Confiável:** LLMs são não-determinísticos e devem ser contidos; suas saídas só entram no estado de domínio através de validação estrita.
* **Múltiplos Destinos:** A publicação ocorre de maneira diversificada para LinkedIn, Facebook, Instagram e Bluesky, demandando isolamento dos Adapters.
* **Rastreabilidade Factual:** É necessário saber de qual versão de qual artigo um post gerado se derivou.
* **Tolerância a Falhas em Integrações:** Integrações de terceiros falham (APIs sociais ou LLMs) e precisam de idempotência, retries e isolamento.

---

## 5. System Context

O JincSAE atua como o mediador autônomo entre o CMS que produz a verdade (WordPress), os motores probabilísticos (LLMs), os humanos que garantem a política editorial, e os canais de distribuição.

*(Veja `diagrams/c4-context.mmd` para o diagrama detalhado de Contexto)*

**Fronteira do Sistema (JincSAE Engine):**
Responsável por orquestrar a ingestão, acionar LLMs via adaptadores, armazenar versões, aplicar validações e agendar publicações aprovadas.

**Sistemas Externos Isolados:**

* **WordPress:** Fonte da verdade (Truth Source).
* **LLM Providers:** Motores genéricos probabilísticos.
* **Social Platforms:** Destinos das publicações.

---

## 6. Architectural Constraints (Derived from the Engineering Constitution)

Estes princípios são mandatórios e fundamentam o design do sistema:

1. **Artigo como Fonte Canônica:** O artigo publicado é a fonte canônica de referência factual do pipeline.
2. **LLMs são Probabilísticos e Não Confiáveis:** Nenhuma saída de LLM se torna estado confiável sem validação.
3. **Rastreabilidade Explicita:** Article → Editorial Analysis → Editorial Brief → Generated Content → Validation → Approval → Publication.
4. **Separação de Geração e Publicação:** Generation e Publication são responsabilidades arquiteturalmente separadas.
5. **Autoridade Humana:** O workflow preserva a autoridade editorial humana.
6. **Estados e Transições Explícitas:** Transições críticas são modeláveis, explícitas e auditáveis.
7. **Independência do Domínio:** O domínio não depende de SDKs externos, WordPress ou provedores de IA.
8. **Isolamento de Sistemas Externos:** Sistemas externos são envelopados por adapters.

---

## 7. Proposed Architectural Style

**Decisão Recomendada:** *Hexagonal Architecture (Ports and Adapters)* ou *Modular Monolith*.

**Rationale:**
Dada a restrição de que o Domínio não deve depender de SDKs externos ou do provedor LLM, o uso de abstrações isoladas obriga a proteção do "Core" de negócio. O fluxo do JincSAE orquestra adaptadores externos (WordPress Ingestion Webhook como *Driver Adapter*, e LLM API/Social APIs como *Driven Adapters*), garantindo que as lógicas e regras de validação (Acessibilidade, Identidade Editorial) residam em serviços puros de aplicação/domínio. A estrutura será mantida modular e pragmática, evitando complexidade distribuída prematura.

*(Essa decisão será alvo de um ADR para consolidação final da linguagem e stack).*

---

## 8. Logical Architecture

As seguintes lógicas devem coexistir modularmente:

* **Ingestion Module:** Recebe e normaliza o webhook de artigo do WP.
* **Analysis & Briefing Module:** Controla o adapter do LLM, requisita a estrutura de briefing e aplica o *Trusted Validation*.
* **Generation Module:** Usa o *Editorial Brief* como entrada para instruir o LLM a gerar as variantes (Platform-specific).
* **Validation Engine:** Agrega as verificações Determinísticas e gerencia a Avaliação Probabilística assistida por IA.
* **Approval & Workflow Module:** Trata o ciclo de vida e versões do conteúdo pendente, registrando a aprovação humana.
* **Publication & Scheduler Module:** Executa a entrega aos canais no tempo correto, via interfaces isoladas.

---

## 9. Dependency Direction

```text
Adapters (HTTP Webhooks, LLM SDKs, Social SDKs, DB Drivers)
      │ depend on
      ▼
Application Use Cases (IngestArticle, GenerateSocialContent)
      │ depend on
      ▼
Domain Layer (Candidate Concepts: Article, Brief, Validation, Approval)
```

O domínio define *Interfaces/Ports*, e a camada de infraestrutura/adapters os implementa.

---

## 10. Domain Architecture

### Candidate Domain Concepts

Os seguintes conceitos de domínio devem ser mapeados (a classificação tática definitiva de Aggregates/Entities pertencerá ao futuro Domain Model):

* **`Article`:** Representa a fonte da verdade. Contém Hash, URL, Conteúdo e Metadados.
* **`EditorialBrief`:** A estrutura validada resultante da análise. Amarrada a um `Article`.
* **`SocialContent` e `ContentVersion`:** Representa o conteúdo gerado para uma rede. Permite rastrear múltiplas versões de uma mesma intenção de publicação.
* **`ValidationResult`:** Provas anexas aos conteúdos de que as regras (Acessibilidade, Formato) foram atendidas.
* **`ApprovalDecision`:** Registro explícito da intervenção humana (quem aprovou/rejeitou, quando e com quais edições).
* **`PublicationAttempt`:** Rastreamento do esforço de entregar o conteúdo na rede social (inclindo target platform, attempt identifier, status, timestamps, retry count, external publication identifier, failure reason).

### Máquina de Estados e Regeneração

Cada *Versão* de Conteúdo deve possuir um estado imutável rastreável (ex: `GENERATED` → `VALIDATED` → `PENDING_REVIEW` → `APPROVED` → `SCHEDULED` → `PUBLISHED`).

**Regeneration Strategy:**
A Regeneração editorial *não* deve ser tratada como um simples recuo na máquina de estados da mesma entidade. Deve ser processada como um evento de workflow (ex: `ContentRegenerationRequested`) que acarreta na criação de uma nova `ContentVersion` (Preservando a rastreabilidade e histórico do ciclo: Article → Brief → ContentVersion 1 → ContentVersion 2).

---

## 11. Application Architecture (Use Cases)

A camada de Aplicação coordena a execução. Casos de uso candidatos incluem o ciclo de vida principal:

* `IngestArticleUseCase(payload)`
* `AnalyzeArticleUseCase(articleId)`
* `GeneratePlatformContentUseCase(briefId, platform)`
* `RegenerateContentUseCase(contentVersionId, feedback)`
* `RunContentValidationUseCase(contentVersionId)`
* `ApproveContentUseCase(contentVersionId, editorId)`
* `PublishContentUseCase(contentVersionId)`

**Concurrency-Safe Idempotency Strategy:**
O MVP priorizará mecanismos simples e transacionais para garantir que webhooks duplicados não corrompam o sistema. Estratégias como *idempotency keys*, *unique constraints* no banco e *duplicate detection* devem ser usadas no `IngestArticleUseCase` no lugar de infraestruturas complexas de lock distribuído.

---

## 12. AI / LLM Architecture

**Fronteira Clara:**
O sistema deve definir interfaces abstratas de análise e geração. O adaptador do LLM converte a chamada em requisições de API reais.

**Componentes Confiáveis vs Probabilísticos:**
A saída do adaptador de LLM é sempre considerada **Probabilística (Untrusted)** até passar pelo validador. Apenas saídas validadas estruturalmente são promovidas ao domínio interno.

---

## 13. Validation Architecture

A arquitetura de validação divide-se em duas categorias de responsabilidade rígida:

### Trusted Validation (Determinística)

* **Schema & Estrutura:** Garante que a saída (ex: JSON) está correta antes de entrar no sistema de domínio.
* **Acessibilidade:** Verificação de regras claras (limite de hashtags, emojis, comprimento).
* **Regras de Plataforma:** Restrições rígidas da rede destino.

### AI-Assisted Evaluation (Probabilística)

* **Detecção de Risco Factual:** Uso secundário de IA para sinalizar possíveis alucinações.
* **Avaliação Editorial:** Sinalização para revisão humana se o tom estiver fora do padrão.
*(Nota: Uma avaliação assistida por IA não é uma prova factual determinística, servindo apenas de apoio à decisão humana).*

---

## 14. Authentication Boundary (Human Identity)

**[PROPOSED - UNDECIDED]**

O sistema requer uma estratégia conceitual de identidade para rastrear humanos nas operações da "Equipe Editorial" que revisam, editam, aprovam e agendam conteúdos.

A decisão específica sobre o provedor (se usará OAuth, JWT próprio ou integração de sessão nativa via WordPress Authentication) é deixada aberta. A arquitetura exige apenas que as ações de domínio (ex: `ApproveContentUseCase`) recebam um identificador autorizativo válido do revisor/autor.

---

## 15. Retry & Processing Architecture

A arquitetura separa os conceitos para lidar com falhas de forma independente. As estratégias de retry **não** devem ser confundidas na máquina de estados de aprovação do conteúdo:

* **Technical Retry:** Tentativas curtas e automáticas na camada de infraestrutura (ex: falhas de rede ao chamar a API do LLM).
* **Editorial Regeneration:** Um evento de negócios deliberado onde o conteúdo é recriado (nova versão) porque não atende ao padrão de qualidade.
* **Publication Retry:** Uma nova `PublicationAttempt` registrada caso a rede social retorne um erro temporário (ex: 503 ou Rate Limit).
* **Nova Tentativa Pós-Falha Permanente:** Requer intervenção manual da equipe após uma falha irrecuperável de integração.

---

## 16. Event and Queue Architecture

**[PROPOSED - UNDECIDED]**

Dada a natureza assíncrona das integrações externas, o processamento de eventos do JincSAE necessita tratar timeouts e agendamentos.

**Alternativas em análise para o MVP:**

1. *Processamento Síncrono Limitado*: Desaconselhado devido a delays e falhas externas.
2. *Background Jobs / Task Queues (ex: Celery ou BullMQ + Redis)*: Uma fila robusta tradicional garante resiliência sem overhead excessivo.
3. *Workflow Engine (ex: Temporal.io)*: Garante sagas e durabilidade, mas pode introduzir complexidade distribuída prematura para o MVP.

A arquitetura do MVP evitará introduzir plataformas de workflow distribuídas antes que os requisitos de negócio realmente justifiquem a complexidade.

---

## 17. Persistence Architecture

**[PROPOSED - UNDECIDED]**

O JincSAE requer rastreabilidade relacional, auditoria contínua, e suporte a transações ACID seguras para gerenciar os ciclos de aprovação e concorrência simples.

* Banco de Dados Relacional clássico (PostgreSQL) como forte candidato.
*(Requer ADR para decisão final).*

---

## 18. External Integration Architecture

* **WordPress Adapter:** Endpoint para ingestão via webhook (com checagem de idempotência na base).
* **LLM Adapters:** Isolamento do Vendor.
* **Social Adapters:** Lidam separadamente com as restrições e esquemas de publicação de cada rede de forma abstraída.

---

## 19. Security Architecture

* **Segredos:** Credenciais estritamente em ambiente/Vault.
* **Autenticação Inbound:** Validação criptográfica de webhooks.
* **Autenticação Outbound:** OAuth Tokens para mídias isolados sem exposição.

---

## 20. Observability and Auditability

Os logs estruturados rastreiam as transições e as provas de auditoria. Toda aprovação humana e cada `PublicationAttempt` deve ser imutável e verificável para suportar o princípio Constitucional da "ausência de falha silenciosa".
