# GENESIS v2.0 — CustomAIAgent (Agent 8)
**Status:** ✅ LIVE | **Endpoints:** 6 | **Base URL:** `/api/v1/genesis`

## Overview
CustomAIAgent creates, trains, and deploys custom AI agents with specific capabilities and behavior customization.

---

## Endpoints

### 1️⃣ GET `/info`
**Metadata and capabilities**
```json
{
  "id": "genesis",
  "name": "CustomAIAgent v2.0",
  "endpoints": 6,
  "status": "active",
  "ai_models": ["claude", "gpt", "local-llm"]
}
```

### 2️⃣ POST `/create-custom-agent`
**Create a new custom AI agent**
- `agent_name` (string): Alphanumeric + underscore (required)
- `description` (string): Agent purpose (min 10 chars)
- `capabilities` (string): JSON array of capabilities

**Response:**
```json
{
  "status": "success",
  "agent_id": "agent_customer_support_123",
  "status": "created",
  "version": "1.0.0",
  "capabilities": 5,
  "initialized_at": "2026-09-28T12:00:00Z"
}
```

**Example:**
```powershell
$uri = "http://127.0.0.1:8000/api/v1/genesis/create-custom-agent?" +
       "agent_name=customer_support&" +
       "description=AI%20agent%20for%20customer%20support%20automation&" +
       "capabilities=%5B%22chat%22,%22ticket_routing%22,%22faq_search%22%5D"
Invoke-WebRequest -Uri $uri -Method POST
```

### 3️⃣ POST `/train-agent`
**Train agent with custom dataset**
- `agent_id` (string): Target agent
- `training_data_size` (integer): Number of training samples (min=10)

**Response:**
```json
{
  "status": "success",
  "training_id": "train_agent_customer_support_123",
  "status": "in_progress",
  "data_size": 1000,
  "epochs": 10,
  "eta_minutes": 45,
  "progress": 0,
  "started_at": "2026-09-28T12:05:00Z"
}
```

### 4️⃣ POST `/invoke-agent`
**Execute agent with prompt**
- `agent_id` (string): Target agent
- `prompt` (string): User query/instruction
- `model` (string): `claude`, `gpt`, `local-llm` (default=`claude`)

**Response:**
```json
{
  "status": "success",
  "response_id": "resp_agent_customer_support_123",
  "model": "claude",
  "response": "I can help you with your issue. Please provide more details...",
  "tokens_used": 234,
  "latency_ms": 345.2,
  "confidence_score": 0.92
}
```

### 5️⃣ GET `/agent-performance`
**Get agent performance metrics**
- `agent_id` (optional, string): Filter by specific agent

**Response:**
```json
{
  "status": "success",
  "agents": 2,
  "performance": {
    "accuracy": 92.5,
    "precision": 89.3,
    "recall": 91.2,
    "f1_score": 90.2,
    "latency_ms": 345.2,
    "cost_per_call": 0.015,
    "uptime_percent": 99.8,
    "total_invocations": 15420,
    "successful_responses": 15138
  }
}
```

### 6️⃣ POST `/customize-behavior`
**Adjust agent behavior parameters**
- `agent_id` (string): Target agent
- `parameter` (string): Parameter name
- `value` (string): New parameter value

**Response:**
```json
{
  "status": "success",
  "customization_id": "custom_agent_customer_support_123",
  "parameter": "temperature",
  "value": 0.7,
  "updated": true,
  "effective_at": "2026-09-28T12:10:00Z"
}
```

---

## AI Model Selection

| Model | Speed | Accuracy | Cost | Best For |
|-------|-------|----------|------|----------|
| **claude** | Medium | Very High | Medium | Complex reasoning, support |
| **gpt** | Fast | High | Low | General purpose, chat |
| **local-llm** | Very Fast | Medium | None | Real-time, on-premise |

---

## Customizable Parameters

```json
{
  "temperature": 0.0-2.0,        // Response creativity (0=deterministic, 2=creative)
  "max_tokens": 100-4096,        // Response length limit
  "top_p": 0.0-1.0,              // Nucleus sampling
  "frequency_penalty": 0.0-2.0,  // Reduce repetition
  "presence_penalty": 0.0-2.0,   // Encourage new topics
  "timeout_seconds": 5-300       // Max response time
}
```

---

## Agent Lifecycle

```
Created → Trained → Deployed → Invoked → Monitored
   ↓         ↓          ↓         ↓          ↓
  1.0      1.1        1.1      1.1       Analytics
                      (live)    (live)
```

---

## Training Strategy

| Size | Duration | Accuracy |
|------|----------|----------|
| 10-100 | 5 min | 65% |
| 100-1k | 15 min | 78% |
| 1k-10k | 45 min | 88% |
| 10k+ | 120+ min | 92%+ |

---

## Response Quality Factors

1. **Model Selection** - Claude (highest accuracy), GPT (balanced), Local (fastest)
2. **Training Data** - Quality > Quantity
3. **Parameters** - Temperature, penalties, limits
4. **Context** - Agent capabilities and constraints
5. **Prompt Engineering** - Clear, specific instructions

---

## Security Rules
✅ Agent name validation (alphanumeric + underscore)  
✅ Description min length: 10 characters  
✅ Training data size: min 10 samples  
✅ Model validation (3 types only)  
✅ Parameter range validation  
✅ Timeout limits: 5-300 seconds  

---

## Error Handling
- Invalid `agent_name` → `{"status": "error"}`
- Description too short → `{"status": "error"}`
- Training data < 10 → `{"status": "error"}`
- Invalid `model` → `{"status": "error"}`
- Agent not found → `{"status": "error"}`
- Invalid parameter → `{"status": "error"}`

---

## Example: Create → Train → Invoke Workflow

```powershell
# 1. Create agent
POST /api/v1/genesis/create-custom-agent?agent_name=support_bot&...

# 2. Train with data
POST /api/v1/genesis/train-agent?agent_id=agent_support_bot_123&training_data_size=1000

# 3. Invoke with query
POST /api/v1/genesis/invoke-agent?agent_id=agent_support_bot_123&prompt=How%20to%20reset%20password

# 4. Monitor performance
GET /api/v1/genesis/agent-performance?agent_id=agent_support_bot_123

# 5. Customize behavior
POST /api/v1/genesis/customize-behavior?agent_id=agent_support_bot_123&parameter=temperature&value=0.7
```
