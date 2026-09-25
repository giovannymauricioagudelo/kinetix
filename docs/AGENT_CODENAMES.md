# Codenames de agentes AFP (Kinetix Studio)

Identidad pública del proyecto. Las clases legacy se mantienen en código por compatibilidad.

| Codename | Legacy (clase) | Rol |
|----------|------------------|-----|
| **Nexus** | DatabaseAgent | El núcleo de conexión de datos. |
| **Synapse** | APIsAgent | Los impulsos que conectan con el exterior. |
| **Matrix** | BusinessRulesAgent | El motor que procesa las reglas del negocio. |
| **Insight** | ReportingAgent | El encargado de reflejar las métricas y reportes. |
| **Prism** | QAAgent | El guardián que analiza y asegura la calidad. |
| **Orbit** | GitDeploymentAgent | El que pone la aplicación en órbita (producción). |
| **Vector** | DevelopmentAgent | El taller principal donde se moldea el código. |

Fuente de verdad en código: `src/agents/agent_catalog.py`.
