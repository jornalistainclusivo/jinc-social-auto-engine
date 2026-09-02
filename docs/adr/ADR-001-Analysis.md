# ADR-001 Decision Analysis: Runtime Language & Core Application Stack

**Status:** PROPOSED FOR HUMAN DECISION

## 1. Decision Context
O `jinc-social-engine` requer uma base sólida de desenvolvimento que orquestrará integrações assíncronas, validações estritas de saídas de LLM, interações com APIs de mídias sociais e persistência estruturada relacional. A escolha da linguagem e stack base ditará a facilidade de implementação da Arquitetura Hexagonal, performance de I/O, segurança de tipos e manutenibilidade a longo prazo.

## 2. Constraints
Derivadas do PRD, Engineering Constitution e SDD:
- **Zero-Trust com AI:** Obrigatoriedade de `Schema validation` determinístico antes que dados toquem o domínio.
- **Isolamento de Domínio:** O Core não pode acoplar-se aos SDKs de plataformas externas ou providers LLM, requerendo forte uso de interfaces e adaptadores (Hexagonal Architecture).
- **Idempotência e Sincronismo:** Alta carga de I/O (Webhooks recebidos vs APIs externas chamadas), necessitando de Background Jobs e processamento assíncrono resiliente.
- **Rastreabilidade:** Necessidade de manipulação clara de modelos de dados transacionais para a persistência relacional.

## 3. Decision Drivers
1. AI/LLM ecosystem (Peso: Alto)
2. Structured outputs (Peso: Crítico)
3. Schema validation (Peso: Crítico)
4. Domain/application architecture support (Peso: Alto)
5. Background jobs (Peso: Alto)
6. Async processing (Peso: Alto)
7. API development (Peso: Médio)
8. Type safety (Peso: Alto)
9. Testing ecosystem (Peso: Médio)
10. Observability (Peso: Médio)
11. Database ecosystem (Peso: Alto)
12. Social platform SDK/API integration (Peso: Médio)
13. Maintainability (Peso: Alto)
14. Developer Experience no VS Code (Peso: Médio)
15. Compatibilidade com Antigravity e desenvolvimento agent-assisted (Peso: Médio)
16. Long-term maintainability (Peso: Alto)
17. Operational complexity (Peso: Alto)
18. Ecosystem stability (Peso: Médio)

---

## 4. Option A — Python

O ecossistema Python é o padrão de fato para Data Science e Machine Learning.

* **Strengths:**
  - Ecossistema IA imbatível; APIs oficiais de provedores LLM (OpenAI, Anthropic) têm adoção *first-class*.
  - Pydantic é o padrão-ouro da indústria para Schema Validation estruturado e validação de outputs LLM (via ferramentas como *Instructor*).
  - FastAPI oferece desenvolvimento web incrivelmente rápido e intuitivo.
  - SQLAlchemy provê ORM maduro para operações relacionais complexas.
* **Weaknesses:**
  - *Type Safety* (MyPy/Pyright) é adicionado tardiamente (bolted-on) e frequentemente requer *workarounds* ou sacrifica expressividade em arquiteturas complexas baseadas em interfaces.
  - Modelagem de abstrações para Ports & Adapters pode parecer *un-pythonic* e excessivamente burocrática se estrita.
  - Ecossistema Assíncrono (`asyncio`) é maduro mas fragmentado quando combinado com bibliotecas antigas sincronas, gerando riscos de gargalos de concorrência.
  - Background Jobs (Celery) exigem infraestrutura mais pesada ou configurações sensíveis.
* **Risks:**
  - A falsa impressão de ser uma ferramenta de "IA" (Machine Learning pipeline) pode obscurecer o fato de que o sistema é primariamente de **Orquestração I/O e Webhooks**.
  - Fragilidade em refatorações massivas em larga escala devido ao sistema de tipagem dinâmico.

---

## 5. Option B — TypeScript (Node.js)

O ecossistema TypeScript construído sobre o V8 (Node.js) é o líder no desenvolvimento web assíncrono.

* **Strengths:**
  - *Async por natureza*: Seu *Event Loop* é arquitetado nativamente para orquestração massiva de I/O e webhooks.
  - *Type Safety e Interfaces*: Permite a implementação da Arquitetura Hexagonal de forma polimórfica e natural, protegendo ativamente os limites do domínio.
  - Validação garantida através do **Zod**, alinhado ao **Vercel AI SDK**, cobrindo brilhantemente o driver de *Structured Outputs*.
  - Ferramentas de Background Jobs incrivelmente robustas e integradas (ex: BullMQ baseado em Redis).
  - Integrações nativas e ricas em SDKs oficiais para Redes Sociais, todas consumindo JSON naturalmente.
  - Ferramentas de banco (Prisma / Drizzle ORM) com o mais alto grau de *Type Safety* da atualidade.
* **Weaknesses:**
  - O ecossistema LLM muitas vezes lança funcionalidades para Python antes do TypeScript, obrigando o uso de ferramentas agnósticas (HTTP puro) em casos muito inovadores.
  - Fadiga do Ecossistema: Elevado número de frameworks web e dependências.
* **Risks:**
  - Complexidade gerencial do `node_modules` e atualizações de segurança frequentes.

---

## 6. Comparative Matrix

| Critério | Python | TypeScript | Vantagem |
| :--- | :--- | :--- | :--- |
| **1. AI/LLM ecosystem** | Nativo e dominante. | Forte adoção (Vercel AI). | **Python** |
| **2. Structured outputs** | Excelente (Instructor/Pydantic). | Excelente (Vercel AI SDK / Zod). | **Empate** |
| **3. Schema validation** | Pydantic (Rust-backed, ultrarrápido). | Zod (Expressivo e nativo da tipagem TS). | **Empate** |
| **4. Domain/app arch support** | Razoável (pouca cultura de interface polimórfica). | Excepcional (Cultura madura de Interfaces/Inversão).| **TypeScript** |
| **5. Background jobs** | Celery (Pesado), RQ. | BullMQ (Rápido, enxuto, baseado em Redis). | **TypeScript** |
| **6. Async processing** | `asyncio` (pode ter atritos com libs legadas). | Nativo (Event Loop). | **TypeScript** |
| **7. API development** | FastAPI (Classe mundial). | Express/NestJS/Hono (Altamente consolidados). | **Empate** |
| **8. Type safety** | MyPy/Pyright (Secundário). | Estrutural e integrado à compilação (Primário). | **TypeScript** |
| **9. Testing ecosystem** | Pytest (Pragmático). | Jest/Vitest (Muito rápidos e isolados). | **Empate** |
| **10. Observability** | OpenTelemetry maduro. | OpenTelemetry maduro + Integrações APM cloud. | **Empate** |
| **11. Database ecosystem** | SQLAlchemy / Alembic (Muito sólido). | Prisma / Drizzle (Melhor DX e Type Safety). | **TypeScript** |
| **12. Social platform SDK/API** | Limitado, mas funcional via bibliotecas HTTP. | Ubíquo (padrão JSON nativo). | **TypeScript** |
| **13. Maintainability** | PEP8, Black. Focado em legibilidade concisa. | Strict Mode impõe rigor em refatorações grandes. | **TypeScript** |
| **14. DX no VS Code** | Pylance é muito bom. | Integração TS Server é impecável e quase imediata. | **TypeScript** |
| **15. Antigravity & Agent-assisted** | Muito boa compreensão sintática. | Extremamente fluente em gerar código web/TS. | **Empate** |
| **16. Long-term maintainability** | Pode escalar mal se tipos forem negligenciados. | Tipagem estrutural protege a integridade do domínio. | **TypeScript** |
| **17. Operational complexity** | Gunicorn/Uvicorn, venv/poetry. | `npm start` em containers simples. | **TypeScript** |
| **18. Ecosystem stability** | Extremamente estável e resiliente. | Alto *churn* em bibliotecas UI, porém Node no backend é sólido. | **Python** |

---

## 7. Consequences

### Caso o TypeScript seja escolhido:
- **Arquiteturais:** O sistema favorecerá interfaces ricas, o que facilitará mockar LLMs e serviços sociais em testes unitários seguindo a Arquitetura Hexagonal.
- **Operacionais:** Executará de forma nativa e assíncrona o alto volume de requisições de I/O necessárias para consultar APIs. O pipeline de CI será simples utilizando ferramentas como Docker e `pnpm`.
- **Técnicas:** Garantirá rastreabilidade e prevenção de erros em tempo de compilação durante toda a passagem de estado.

### Caso o Python seja escolhido:
- **Arquiteturais:** Exigirá forte vigilância em testes estáticos (`mypy --strict`) para evitar que dinâmismos quebrem a estrutura restrita de aprovação delineada na Constituição.
- **Operacionais:** Exigirá infraestrutura separada para os workers assíncronos que chamam as APIs lentas de IA.
- **Técnicas:** Maior facilidade para implementar algoritmos pesados de PLN (Processamento de Linguagem Natural) ou integrações complexas de Data Science, **que não são o escopo do MVP**.

---

## 8. Recommendation

Recomendo a adoção do **TypeScript (Node.js)** com **Zod**, **Drizzle/Prisma ORM**, e **BullMQ**.

**Motivo:** Embora seja um projeto que interage com IA, o `jinc-social-engine` não é um projeto de treinamento de modelos ou data pipelines. Ele é um motor puramente transacional de **Orquestração Assíncrona e Webhooks**, cuja maior responsabilidade é validar esquemas e transitar estados de aprovação interagindo com APIs (WordPress, LLMs, Social). Nestas categorias (Async, I/O, Typesafe Domain, e Ports and Adapters), o TypeScript provê ferramentas estruturalmente mais protetoras contra falhas em tempo de execução, cumprindo plenamente a *Engineering Constitution*.

---

## 9. Open Risks

- **Atraso em Features AI:** A OpenAI ou Anthropic costumam liberar *features* experimentais primeiro em SDKs Python.
- *Mitigação:* Como o domínio e adaptação são isolados, as chamadas diretas REST podem ser usadas se o SDK TS atrasar.

---

## 10. Proposed ADR Decision

*(Não formalizado)*
- **Linguagem Base:** TypeScript (Node.js)
- **Runtime:** Node.js (v20+)
- **Package Manager:** pnpm
- **Validation:** Zod
