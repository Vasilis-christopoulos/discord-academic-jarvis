# discord-academic-jarvis

![CI](https://github.com/Vasilis-christopoulos/mcgill-discord-assistant/actions/workflows/ci.yml/badge.svg)

## Phase 0:
This is the initial project structure setup as well as a test bot, to check that the connection between the project and discord is established.

![Screenshot of the application](./screenshots/initial-connection.png)

## Phase 1:

### Features
- `!jarvis rag <query>` in RAG‑enabled channels  
- `!jarvis calendar <query>` in Calendar‑enabled channels  
- `!jarvis <query>` elsewhere for fallback  
- Channel‑aware routing based on `tenants.json`

### Usage Examples
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

## Next Up (Phase 2)
- Integrate Google Calendar API
- Test for date parsing and event lookup
- Verify !jarvis calendar returns real data
