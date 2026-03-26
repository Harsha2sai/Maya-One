import os
import json
import logging
import asyncio
import re
import time
from aiohttp import web
from livekit.api import (
    AccessToken,
    VideoGrants,
    LiveKitAPI,
    CreateRoomRequest,
    CreateAgentDispatchRequest,
)
from livekit.protocol import models, room

logger = logging.getLogger(__name__)

_latest_token_room_context: dict[str, object] = {}
_last_room_by_run_id: dict[str, str] = {}

# Map provider IDs to environment variable names
# Centralized to avoid duplication and inconsistencies
ENV_VAR_MAPPING = {
    'groq': 'GROQ_API_KEY',
    'groq_secondary': 'GROQ_API_KEY_2',
    'groq_tertiary': 'GROQ_API_KEY_3',
    'openai': 'OPENAI_API_KEY',
    'gemini': 'GEMINI_API_KEY',
    'gemini_secondary': 'GEMINI_API_KEY_2',
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
    'livekit_active_slot': 'LIVEKIT_ACTIVE_SLOT',
    'livekit_url': 'LIVEKIT_URL',
    'livekit_api_key': 'LIVEKIT_API_KEY',
    'livekit_api_secret': 'LIVEKIT_API_SECRET',
    'livekit_url_2': 'LIVEKIT_URL_2',
    'livekit_api_key_2': 'LIVEKIT_API_KEY_2',
    'livekit_api_secret_2': 'LIVEKIT_API_SECRET_2',
    'livekit_agent_name': 'LIVEKIT_AGENT_NAME',
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

MULTI_SLOT_LLM_PROVIDER_IDS = {
    'groq',
    'gemini',
    'openai',
    'anthropic',
    'deepseek',
    'mistral',
    'perplexity',
    'together',
    'nvidia',
}


def _livekit_slot_suffix(active_slot: str) -> str:
    """Slot 1/auto -> '', slot N -> _N"""
    slot = str(active_slot or "1").strip()
    if not slot.isdigit():
        return ""
    return "" if slot == "1" else f"_{slot}"


def _resolve_livekit_credentials() -> tuple[str, str, str]:
    active_slot = os.getenv("LIVEKIT_ACTIVE_SLOT", "1").strip()
    suffix = _livekit_slot_suffix(active_slot)
    livekit_url = os.getenv(f"LIVEKIT_URL{suffix}", "").strip()
    livekit_api_key = os.getenv(f"LIVEKIT_API_KEY{suffix}", "").strip()
    livekit_api_secret = os.getenv(f"LIVEKIT_API_SECRET{suffix}", "").strip()
    if not (livekit_url and livekit_api_key and livekit_api_secret):
        raise RuntimeError("LiveKit credentials are missing; cannot complete request")
    return livekit_url, livekit_api_key, livekit_api_secret


def _provider_id_to_env_var(provider_id: str):
    """Translate Flutter settings keys into backend env var names."""
    pid = str(provider_id or "").strip()
    if not pid:
        return None

    if pid in ENV_VAR_MAPPING:
        return ENV_VAR_MAPPING[pid]

    if pid.endswith('_active_key_slot'):
        provider_prefix = pid[:-len('_active_key_slot')].upper()
        return f"{provider_prefix}_ACTIVE_KEY_SLOT"

    if pid.endswith('_active_slot'):
        provider_prefix = pid[:-len('_active_slot')].upper()
        # LiveKit historically uses LIVEKIT_ACTIVE_SLOT (without _KEY_)
        if provider_prefix == 'LIVEKIT':
            return 'LIVEKIT_ACTIVE_SLOT'
        return f"{provider_prefix}_ACTIVE_KEY_SLOT"

    if pid.endswith('_slot_count'):
        provider_prefix = pid[:-len('_slot_count')].upper()
        return f"{provider_prefix}_SLOT_COUNT"

    if pid.startswith('livekit_') or '_api_key_' in pid:
        return pid.upper()

    # Dynamic multi-key UI sends "groq_2", "gemini_3", "openai_2", etc.
    slot_match = re.fullmatch(r'([a-z0-9]+)_(\d+)', pid)
    if slot_match:
        base_provider, slot_num = slot_match.groups()
        if base_provider in MULTI_SLOT_LLM_PROVIDER_IDS:
            return f"{base_provider.upper()}_API_KEY_{slot_num}"

    return None


def _env_var_to_provider_id(env_var: str) -> str:
    """Translate env var names back into Flutter-facing provider keys."""
    reverse_mapping = {v: k for k, v in ENV_VAR_MAPPING.items()}
    if env_var in reverse_mapping:
        return reverse_mapping[env_var]

    if env_var == 'LIVEKIT_ACTIVE_SLOT':
        return 'livekit_active_slot'

    m = re.fullmatch(r'([A-Z0-9]+)_ACTIVE_KEY_SLOT', env_var)
    if m:
        return f"{m.group(1).lower()}_active_slot"

    m = re.fullmatch(r'([A-Z0-9]+)_SLOT_COUNT', env_var)
    if m:
        return f"{m.group(1).lower()}_slot_count"

    m = re.fullmatch(r'([A-Z0-9]+)_API_KEY_(\d+)', env_var)
    if m:
        return f"{m.group(1).lower()}_{m.group(2)}"

    return env_var.lower()

async def _ensure_room_dispatch(room_name: str) -> None:
    """
    Ensure the room has a dispatch targeting LIVEKIT_AGENT_NAME.
    This is required when workers are registered with a non-empty agent_name.
    """
    # Must match worker default so dispatch works even if .env omits the value.
    agent_name = os.getenv("LIVEKIT_AGENT_NAME", "maya-one").strip()
    if not agent_name:
        return

    livekit_url, livekit_api_key, livekit_api_secret = _resolve_livekit_credentials()

    lk = LiveKitAPI(
        url=livekit_url,
        api_key=livekit_api_key,
        api_secret=livekit_api_secret,
    )
    try:
        # Dispatch requires the room to exist first.
        try:
            await lk.room.create_room(CreateRoomRequest(name=room_name))
        except Exception as e:
            # Room already exists is fine; anything else should bubble up.
            if "already exists" not in str(e).lower():
                raise

        listed = await lk.agent_dispatch.list_dispatch(room_name=room_name)
        already_exists = any(d.agent_name == agent_name for d in listed)
        if already_exists:
            return

        await lk.agent_dispatch.create_dispatch(
            CreateAgentDispatchRequest(
                agent_name=agent_name,
                room=room_name,
                metadata='{"source":"token_server"}',
            )
        )
        logger.info(f"✅ Dispatch created for room={room_name}, agent={agent_name}")
    finally:
        await lk.aclose()

async def handle_token(request):
    """Integrated token generation endpoint"""
    try:
        data = await request.json()
        room_name = data.get('roomName')
        participant_name = data.get('participantName')
        metadata = data.get('metadata', {})
        
        if not room_name or not participant_name:
            return web.json_response({'error': 'roomName and participantName required'}, status=400)

        # Ensure this room is routed to the configured worker name.
        # If this fails, returning token would create a silent no-agent session.
        await _ensure_room_dispatch(room_name)
        
        active_slot = os.getenv("LIVEKIT_ACTIVE_SLOT", "1").strip()
        suffix = _livekit_slot_suffix(active_slot)
        
        token = (
            AccessToken(os.getenv(f"LIVEKIT_API_KEY{suffix}"), os.getenv(f"LIVEKIT_API_SECRET{suffix}"))
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
            token = token.with_metadata(json.dumps(metadata))

        _latest_token_room_context.update(
            {
                "room_name": str(room_name),
                "participant_name": str(participant_name),
                "issued_at_ms": int(time.time() * 1000),
            }
        )
        logger.info(
            "send_message_room_context_updated room=%s participant=%s",
            room_name,
            participant_name,
        )
            
        print(f"✅ [Internal] Generated token for {participant_name} in room {room_name}")
        return web.json_response({
            'token': token.to_jwt(),
            'url': os.getenv(f"LIVEKIT_URL{suffix}")
        })
    except Exception as e:
        logger.error(f"❌ Token error: {e}")
        return web.json_response({'error': str(e)}, status=500)


async def handle_send_message(request):
    """Inject a test text message into the latest token-issued LiveKit room."""
    try:
        try:
            data = await request.json()
        except Exception:
            return web.json_response({'error': 'Invalid JSON payload'}, status=400)

        if not isinstance(data, dict):
            return web.json_response({'error': 'Invalid JSON payload'}, status=400)

        message = str(data.get('message') or '').strip()
        if not message:
            return web.json_response({'error': 'message is required'}, status=400)

        user_id = str(data.get('user_id') or '').strip() or 'test_user'
        run_id = str(data.get('run_id') or '').strip()
        room_name = str(_latest_token_room_context.get("room_name") or "").strip()
        if not room_name:
            logger.warning(
                "send_message_rejected_no_room user_id=%s run_id=%s",
                user_id,
                run_id or "-",
            )
            return web.json_response(
                {'error': 'No active token-issued room context yet'}, status=409
            )

        if run_id:
            previous_room = _last_room_by_run_id.get(run_id)
            if previous_room and previous_room != room_name:
                logger.warning(
                    "send_message_room_changed run_id=%s previous_room=%s new_room=%s",
                    run_id,
                    previous_room,
                    room_name,
                )
            _last_room_by_run_id[run_id] = room_name

        livekit_url, livekit_api_key, livekit_api_secret = _resolve_livekit_credentials()
        lk = LiveKitAPI(
            url=livekit_url,
            api_key=livekit_api_key,
            api_secret=livekit_api_secret,
        )
        try:
            payload = message.encode("utf-8")
            await lk.room.send_data(
                room.SendDataRequest(
                    room=room_name,
                    data=payload,
                    kind=models.DataPacket.Kind.Value("RELIABLE"),
                    topic="lk.chat",
                )
            )
        finally:
            await lk.aclose()

        logger.info(
            "send_message_accepted room=%s user_id=%s run_id=%s bytes=%s",
            room_name,
            user_id,
            run_id or "-",
            len(payload),
        )
        return web.json_response(
            {
                'status': 'ok',
                'room': room_name,
                'user_id': user_id,
                'run_id': run_id,
                'bytes': len(payload),
            },
            status=200,
        )
    except Exception as e:
        logger.error(
            "send_message_failed error=%s",
            e,
            exc_info=True,
        )
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
        
        from dotenv import set_key
        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
        
        # Ensure .env exists
        if not os.path.exists(env_path):
            with open(env_path, 'w') as f:
                f.write("")
        
        def _resolve_gemini_oauth_env(provider_id: str) -> str | None:
            if provider_id in {"gemini", "gemini_1"}:
                return "GEMINI_OAUTH_ACCESS_TOKEN"
            if provider_id in {"gemini_2", "gemini_secondary"}:
                return "GEMINI_OAUTH_ACCESS_TOKEN_2"
            return None

        # Update with new keys
        updated_count = 0
        for provider_id, api_key in api_keys.items():
            # Handle Gemini OAuth access tokens sent as "OAUTH:<token>"
            if isinstance(api_key, str) and api_key.startswith("OAUTH:"):
                oauth_env = _resolve_gemini_oauth_env(provider_id)
                if oauth_env:
                    token = api_key[len("OAUTH:"):].strip()
                    if token:
                        os.environ[oauth_env] = token
                        set_key(env_path, oauth_env, token)
                        updated_count += 1
                        logger.info(f"✅ Updated {oauth_env}")
                        continue

            env_var = _provider_id_to_env_var(provider_id)

            if env_var and api_key is not None:
                # Also set in current environment
                os.environ[env_var] = str(api_key)
                set_key(env_path, env_var, str(api_key))
                updated_count += 1
                logger.info(f"✅ Updated {env_var}")

        if updated_count > 0:
            # Ensure new credentials are picked up by freshly resolved providers.
            try:
                from providers.factory import ProviderFactory
                ProviderFactory.reset_cache()
            except Exception as cache_err:
                logger.warning(f"⚠️ Failed resetting provider cache after API key sync: {cache_err}")

            try:
                from config.settings import reload_settings
                reload_settings()
            except Exception as settings_err:
                logger.warning(f"⚠️ Failed reloading settings after API key sync: {settings_err}")
        
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
        
        # Base mappings
        mapping = dict(ENV_VAR_MAPPING)

        # Add dynamic mappings from environment
        for env_var in os.environ:
            if (
                env_var.endswith('_API_KEY')
                or '_API_KEY_' in env_var
                or env_var.endswith('_ACTIVE_KEY_SLOT')
                or env_var.endswith('_ACTIVE_SLOT')
                or env_var.endswith('_SLOT_COUNT')
                or env_var.startswith('LIVEKIT_')
            ) and env_var not in mapping.values():
                provider_id = _env_var_to_provider_id(env_var)
                mapping[provider_id] = env_var

        for provider_id, env_var in mapping.items():
            # Filter only pertinent keys for status
            if provider_id in ['llmprovider', 'llmmodel', 'sttprovider', 'sttmodel', 'sttlanguage', 'ttsprovider', 'ttsmodel', 'ttsvoice']:
                continue
                
            value = str(os.getenv(env_var, ''))
            status[provider_id] = bool(value)
            is_control_value = (
                env_var.endswith('_ACTIVE_KEY_SLOT')
                or env_var.endswith('_ACTIVE_SLOT')
                or env_var.endswith('_SLOT_COUNT')
            )
            if is_control_value:
                masked[provider_id] = value
            elif value and len(value) > 8:
                masked[provider_id] = f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"
            elif value:
                masked[provider_id] = '*' * len(value)
            else:
                masked[provider_id] = ''

        # Gemini OAuth tokens should count as configured for status/masking.
        gemini_oauth_1 = os.getenv("GEMINI_OAUTH_ACCESS_TOKEN", "").strip()
        gemini_oauth_2 = os.getenv("GEMINI_OAUTH_ACCESS_TOKEN_2", "").strip()
        if gemini_oauth_1:
            status["gemini"] = True
            if not masked.get("gemini"):
                masked["gemini"] = f"{gemini_oauth_1[:4]}{'*' * max(0, len(gemini_oauth_1) - 8)}{gemini_oauth_1[-4:]}"
        if gemini_oauth_2:
            status["gemini_2"] = True
            if not masked.get("gemini_2"):
                masked["gemini_2"] = f"{gemini_oauth_2[:4]}{'*' * max(0, len(gemini_oauth_2) - 8)}{gemini_oauth_2[-4:]}"
        
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
