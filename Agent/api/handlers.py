import os
import json
import logging
import asyncio
from aiohttp import web
from livekit.api import AccessToken, VideoGrants

logger = logging.getLogger(__name__)

# Map provider IDs to environment variable names
# Centralized to avoid duplication and inconsistencies
ENV_VAR_MAPPING = {
    'groq': 'GROQ_API_KEY',
    'openai': 'OPENAI_API_KEY',
    'gemini': 'GEMINI_API_KEY',
    'anthropic': 'ANTHROPIC_API_KEY',
    'deepseek': 'DEEPSEEK_API_KEY',
    'mistral': 'MISTRAL_API_KEY',
    'perplexity': 'PERPLEXITY_API_KEY',
    'together': 'TOGETHER_API_KEY',
    'deepgram': 'DEEPGRAM_API_KEY',
    'assemblyai': 'ASSEMBLYAI_API_KEY',
    'cartesia': 'CARTESIA_API_KEY',
    'elevenlabs': 'ELEVENLABS_API_KEY',
    'mem0': 'MEM0_API_KEY',
    'aws_access_key': 'AWS_ACCESS_KEY_ID',
    'aws_secret_key': 'AWS_SECRET_ACCESS_KEY',
    'azure_speech_key': 'AZURE_SPEECH_KEY',
    'azure_speech_region': 'AZURE_SPEECH_REGION',
    'azure_speech_endpoint': 'AZURE_SPEECH_ENDPOINT',
    # LiveKit credentials
    'livekit_url': 'LIVEKIT_URL',
    'livekit_api_key': 'LIVEKIT_API_KEY',
    'livekit_api_secret': 'LIVEKIT_API_SECRET',
    # MCP Server
    'n8n_mcp_url': 'N8N_MCP_SERVER_URL',
    # Supabase
    'supabase_url': 'SUPABASE_URL',
    'supabase_anon_key': 'SUPABASE_ANON_KEY',
    'supabase_service_key': 'SUPABASE_SERVICE_KEY',
    # Configuration Settings
    'llmProvider': 'LLM_PROVIDER',
    'llmModel': 'LLM_MODEL',
    'sttProvider': 'STT_PROVIDER',
    'sttModel': 'STT_MODEL',
    'sttLanguage': 'STT_LANGUAGE',
    'ttsProvider': 'TTS_PROVIDER',
    'ttsModel': 'TTS_MODEL',
    'ttsVoice': 'TTS_VOICE', 
}

async def handle_token(request):
    """Integrated token generation endpoint"""
    try:
        data = await request.json()
        room_name = data.get('roomName')
        participant_name = data.get('participantName')
        metadata = data.get('metadata', {})
        
        if not room_name or not participant_name:
            return web.json_response({'error': 'roomName and participantName required'}, status=400)
        
        token = (
            AccessToken(os.getenv("LIVEKIT_API_KEY"), os.getenv("LIVEKIT_API_SECRET"))
            .with_identity(participant_name)
            .with_name(participant_name)
            .with_grants(VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            ))
        )
        
        if metadata:
            token = token.with_metadata(str(metadata))
            
        print(f"✅ [Internal] Generated token for {participant_name} in room {room_name}")
        return web.json_response({
            'token': token.to_jwt(),
            'url': os.getenv("LIVEKIT_URL")
        })
    except Exception as e:
        logger.error(f"❌ Token error: {e}")
        return web.json_response({'error': str(e)}, status=500)

async def handle_health(request):
    """Health check endpoint"""
    return web.json_response({'status': 'ok'})

async def handle_api_keys(request):
    """Sync API keys from Flutter app to backend .env file"""
    try:
        data = await request.json()
        api_keys = data.get('apiKeys', {})
        
        if not api_keys:
            return web.json_response({'error': 'No API keys provided'}, status=400)
        
        # Merge 'config' into api_keys if present (support both legacy and new structure)
        if 'config' in data:
            api_keys.update(data['config'])
        
        # Read existing .env file
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
        existing_lines = []
        existing_keys = {}
        
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key = line.split('=', 1)[0]
                        existing_keys[key] = line
                    existing_lines.append(line)
        
        # Update with new keys
        updated_count = 0
        for provider_id, api_key in api_keys.items():
            if provider_id in ENV_VAR_MAPPING and api_key:
                env_var = ENV_VAR_MAPPING[provider_id]
                new_line = f"{env_var}={api_key}"
                existing_keys[env_var] = new_line
                # Also set in current environment
                os.environ[env_var] = api_key
                updated_count += 1
                print(f"✅ Updated {env_var}")
        
        # Write back .env file
        with open(env_path, 'w') as f:
            written_keys = set()
            for line in existing_lines:
                if line and not line.startswith('#') and '=' in line:
                    key = line.split('=', 1)[0]
                    if key in existing_keys and key not in written_keys:
                        f.write(existing_keys[key] + '\n')
                        written_keys.add(key)
                else:
                    f.write(line + '\n')
            
            # Add any new keys not in original file
            for key, value in existing_keys.items():
                if key not in written_keys:
                    f.write(value + '\n')
        
        return web.json_response({
            'success': True,
            'updated': updated_count,
            'message': f'{updated_count} API keys synced to backend'
        })
        
    except Exception as e:
        logger.error(f"❌ API keys sync error: {e}")
        return web.json_response({'error': str(e)}, status=500)

async def handle_get_api_status(request):
    """Get status of configured API keys (masked)"""
    try:
        status = {}
        masked = {}
        
        for provider_id, env_var in ENV_VAR_MAPPING.items():
            # Filter only pertinent keys for status
            if provider_id in ['llmProvider', 'llmModel', 'sttProvider', 'sttModel', 'sttLanguage', 'ttsProvider', 'ttsModel', 'ttsVoice']:
                continue
                
            value = os.getenv(env_var, '')
            status[provider_id] = bool(value)
            if value and len(value) > 8:
                masked[provider_id] = f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"
            elif value:
                masked[provider_id] = '*' * len(value)
            else:
                masked[provider_id] = ''
        
        # Add combined LiveKit status (true only if all 3 are configured)
        status['livekit'] = all([
            status.get('livekit_url'),
            status.get('livekit_api_key'),
            status.get('livekit_api_secret')
        ])
        
        # Add combined MCP status
        status['n8n_mcp'] = status.get('n8n_mcp_url', False)
        
        # Add combined Supabase status (true only if all 3 are configured)
        status['supabase'] = all([
            status.get('supabase_url'),
            status.get('supabase_anon_key'),
            status.get('supabase_service_key')
        ])
        
        return web.json_response({
            'status': status,
            'masked': masked
        })
        
    except Exception as e:
        logger.error(f"❌ API status error: {e}")
        return web.json_response({'error': str(e)}, status=500)
async def handle_upload(request):
    """Handle file uploads from Flutter app"""
    try:
        reader = await request.multipart()
        field = await reader.next()
        
        if not field:
            return web.json_response({'error': 'No file uploaded'}, status=400)
            
        filename = field.filename
        if not filename:
            # Fallback for some clients
            filename = f"upload_{int(asyncio.get_event_loop().time())}"
            
        uploads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
        os.makedirs(uploads_dir, exist_ok=True)
        
        file_path = os.path.join(uploads_dir, filename)
        
        # Avoid overwriting (basic version)
        if os.path.exists(file_path):
            base, ext = os.path.splitext(filename)
            file_path = os.path.join(uploads_dir, f"{base}_{int(asyncio.get_event_loop().time())}{ext}")
            filename = os.path.basename(file_path)

        size = 0
        with open(file_path, 'wb') as f:
            while True:
                chunk = await field.read_chunk()
                if not chunk:
                    break
                size += len(chunk)
                f.write(chunk)
        
        logger.info(f"✅ File uploaded: {filename} ({size} bytes)")
        
        # Return the public/local URL
        # Assuming the token server port 5050
        file_url = f"http://localhost:5050/uploads/{filename}"
        
        return web.json_response({
            'success': True,
            'filename': filename,
            'url': file_url,
            'size': size
        })
    except Exception as e:
        logger.error(f"❌ Upload error: {e}")
        return web.json_response({'error': str(e)}, status=500)
