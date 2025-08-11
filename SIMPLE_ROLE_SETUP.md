# Simple Role-Based Access Control Setup

Your Discord Academic Jarvis now uses a simplified role-based access control system! 🔒

## Quick Setup (2 Steps)

### Step 1: Get Your Admin Role ID
1. Open Discord and go to your server
2. Go to **Server Settings** → **Roles**
3. Right-click on the role you want to use for admin access (e.g., "admins")
4. Click **Copy ID**
5. You'll get a number like: `987654321098765432`

### Step 2: Update Configuration
Edit `tenants.json` and replace the placeholder with your actual role ID:

```json
{
    "1361356484478500865": {
        "name": "mcgill-mma",
        "description": "McGill MMA server",
        "admin_role_id": 987654321098765432,  ← Replace this number
        "calendar_id": "...",
        ...
    }
}
```

### Step 3: Restart Your Bot
```bash
python main_bot.py
```

## ✅ You're Done!

Users with the specified role can now upload files using `/jarvis_upload`!

## Features

- 🔒 **Secure**: Uses Discord role IDs (immutable)
- 🎯 **Simple**: Just one configuration field
- 🧹 **Clean**: No extra files or complex setup
- 📊 **Integrated**: Works with existing tenant system

## Commands

- `/jarvis_upload` - Upload files (admin only)
- `/jarvis_access` - View access control settings (admin only)
- `/jarvis_stats` - View usage statistics
- `/jarvis_rag` - Ask questions with rate limiting

## Troubleshooting

**Can't find Copy ID option?**
- Enable Developer Mode in Discord: User Settings → Advanced → Developer Mode

**Users with correct role can't upload?**
- Double-check the role ID in tenants.json
- Make sure you restarted the bot
- Use `/jarvis_access` to verify configuration

**Configuration error?**
- Ensure the admin_role_id is a number (no quotes)
- Check JSON syntax is valid

That's it! Simple and effective role-based access control. 🚀
