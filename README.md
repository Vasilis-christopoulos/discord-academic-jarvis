# Discord Academic Jarvis

<!-- Project Overview and Architecture -->
**A multi-tenant Discord bot for academic environments with RAG, Calendar, and Conversational AI capabilities**

## 🏗️ Architecture Overview

This bot follows a modular, multi-tenant architecture designed for academic Discord servers:

### Core Modules
- **RAG Module** (`rag_module/`) - Document-based Q&A using vector databases
- **Calendar Module** (`calendar_module/`) - Google Calendar/Tasks integration with NLP query parsing

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
