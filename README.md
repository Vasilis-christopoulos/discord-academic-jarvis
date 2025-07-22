# Discord Academic Jarvis

<!-- Project Overview and Architecture -->
**A multi-tenant Discord bot for academic environments with RAG, Calendar, and Conversational AI capabilities**

## 🏗️ Architecture Overview

This bot follows a modular, multi-tenant architecture designed for academic Discord servers:

### Core Modules
- **RAG Module** (`rag_module/`) - Document-based Q&A using vector databases
- **Calendar Module** (`calendar_module/`) - Google Calendar/Tasks integration with NLP query parsing

### Tech Stack
- **Discord.py** - Discord bot framework
- **OpenAI API** - Language models for NLP and conversation
- **Pinecone** - Vector database for semantic search
- **Google Calendar/Tasks APIs** - Calendar data integration 
- **Supabase** - Synchronization handling, rate limiting and user stats
- **Pydantic** - Configuration validation and data modeling
- **LangChain** - LLM orchestration and structured outputs

![CI](https://github.com/Vasilis-christopoulos/mcgill-discord-assistant/actions/workflows/ci.yml/badge.svg)

---
