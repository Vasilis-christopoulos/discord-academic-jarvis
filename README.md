# Discord Academic Jarvis

<!-- Project Overview and Architecture -->
**A multi-tenant Discord bot for academic environments with RAG, Calendar, and Conversational AI capabilities**

## 🏗️ Architecture Overview

This bot follows a modular, multi-tenant architecture designed for academic Discord servers:

### Core Modules
- **RAG Module** (`rag_module/`) - Document-based Q&A using vector databases
- **Calendar Module** (`calendar_module/`) - Google Calendar/Tasks integration with NLP query parsing
- **Fallback Module** (`fallback_module/`) - General conversational bot

### Key Components
- **Multi-tenant Configuration** (`tenants.json`, `settings.py`) - Support multiple Discord servers with different configurations
- **Channel-aware Routing** (`message_router.py`) - Per-channel module access control
- **Natural Language Processing** (`calendar_module/query_parser.py`) - LLM-powered query parsing
- **Vector Search** (`utils/hybrid_search_utils.py`) - Semantic search capabilities
- **Comprehensive Logging** (`utils/logging_config.py`) - Structured logging with rotation

### Tech Stack
- **Discord.py** - Discord bot framework
- **OpenAI API** - Language models for NLP and conversation
- **Pinecone** - Vector database for semantic search
- **Google Calendar/Tasks APIs** - Calendar data integration 
- **Supabase** - Synchronization handling 
- **Pydantic** - Configuration validation and data modeling
- **LangChain** - LLM orchestration and structured outputs

![CI](https://github.com/Vasilis-christopoulos/mcgill-discord-assistant/actions/workflows/ci.yml/badge.svg)

---

## 🚀 Development Phases

### Phase 0: Foundation
This is the initial project structure setup as well as a test bot, to check that the connection between the project and discord is established.

![Screenshot of the application](./screenshots/initial-connection.png)

### Phase 1: Core Functionality

#### Features
- `!jarvis rag <query>` in RAG‑enabled channels  
- `!jarvis calendar <query>` in Calendar‑enabled channels  
- `!jarvis <query>` elsewhere for fallback  
- Channel‑aware routing based on `tenants.json`

#### Usage Examples
- In a RAG channel (type = "rag" or "rag-calendar)
```
!jarvis rag What's in the syllabus?
```

- In a calendar channel (type = "calendar" or "rag-calendar")
```
!jarvis calendar When is the next deadline?
```

- In any channel
```
!jarvis How are you today?
```

### Phase 2: Enhanced Integration
- Integrate Google Calendar API
- Test for date parsing and event lookup
- Verify !jarvis calendar returns real data
