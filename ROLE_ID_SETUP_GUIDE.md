# Role ID-Based Access Control Setup Guide

Your Discord Academic Jarvis bot now uses **Role ID-based access control** for enhanced security! 🔒

## Quick Setup (3 Steps)

### Step 1: Find Your Role IDs
```bash
python find_role_ids.py
```

This will show you all roles in your Discord server with their IDs. Look for output like:
```
🏠 Server: My Discord Server (ID: 123456789)
----------------------------------------
  admins               | ID: 987654321098765432 👑
  moderators           | ID: 876543210987654321 👑
  members              | ID: 765432109876543210
```

### Step 2: Configure Access
Edit `access_config.py` and replace the placeholder with your actual role ID:

```python
# Before
ADMIN_ROLE_IDS = [
    123456789012345678,  # Replace with your actual admin role ID
]

# After (example)
ADMIN_ROLE_IDS = [
    987654321098765432,  # admins role
    876543210987654321,  # moderators role (optional)
]
```

### Step 3: Restart Your Bot
```bash
python main_bot.py
```

## ✅ You're Done!

Your bot now has secure, role-based file upload restrictions!

## Features

### 🔒 **Enhanced Security**
- Uses Discord role IDs (more secure than role names)
- Role names can be changed, but IDs never change
- Supports multiple admin roles
- Optional permission-based access (Administrator, Manage Server)

### 🤖 **New Commands**
- `/jarvis_upload` - Upload files (admin only)
- `/jarvis_access` - View access control settings (admin only)
- `/jarvis_stats` - View usage statistics
- `/jarvis_rag` - Ask questions with rate limiting

### 📊 **Access Control Info**
Admins can use `/jarvis_access` to see:
- Which roles have upload access
- Which permissions grant access
- Total number of access methods configured

## Configuration Options

### Multiple Admin Roles
```python
ADMIN_ROLE_IDS = [
    987654321098765432,  # admins
    876543210987654321,  # moderators
    765432109876543210,  # trusted-users
]
```

### Permission-Based Access
```python
ALLOW_ADMINISTRATOR_PERMISSION = True   # Users with "Administrator" can upload
ALLOW_MANAGE_GUILD_PERMISSION = False   # Users with "Manage Server" can upload
```

## User Experience

### ✅ **Admin Users**
- Can upload files normally
- See detailed upload validation
- Get usage statistics
- Can view access control settings

### ❌ **Non-Admin Users**
- Get clear "Access Denied" message
- See which role IDs have access
- See their current role IDs for troubleshooting
- See their role names for reference

### 📱 **Example Error Message**
```
❌ Access Denied
You need admin permissions to upload files.

Required Role IDs: 987654321098765432
Your Role IDs: 765432109876543210, 654321098765432109
Your Roles: members, students
```

## Troubleshooting

### "No roles found" when running find_role_ids.py
- Make sure your bot is added to your Discord server
- Check that your Discord token is correct in settings
- Ensure the bot has permission to see roles

### Users with correct role can't upload
- Double-check the role ID in `access_config.py`
- Make sure you restarted the bot after changing the config
- Use `/jarvis_access` to verify the configuration

### Role ID vs Role Name
- **Role IDs** are numbers (e.g., 987654321098765432)
- **Role Names** are text (e.g., "admins")
- This system uses IDs for better security

## Security Benefits

1. **Immutable**: Role IDs never change, even if role names are changed
2. **Precise**: No confusion from similar role names
3. **Flexible**: Support multiple roles and permission-based access
4. **Transparent**: Clear error messages help with troubleshooting
5. **Auditable**: Admins can view exactly which roles have access

Your Discord Academic Jarvis is now production-ready with enterprise-grade access control! 🚀
