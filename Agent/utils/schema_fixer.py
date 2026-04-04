"""
Tool Schema Fixer for LiveKit Agents

This module patches LiveKit's schema builder functions to ensure all generated
tool schemas are compliant with strict OpenAI/Groq JSON Schema requirements.

The bug: LiveKit's build_legacy_openai_schema and build_strict_openai_schema 
functions ensure 'required' exists but forget to ensure 'properties' exists.
This causes validation errors for tools with zero parameters.

Fix: Monkey patch both functions to add 'properties': {} when missing.
"""

import logging

logger = logging.getLogger(__name__)

_patched = False

def apply_schema_patch(provider_name: str | None = None):
    """Apply the schema fix patch to LiveKit's schema builder functions.

    OpenAI keeps strict tool schemas enabled. Non-OpenAI providers use the
    compatibility shim that forces strict_tool_schema off.
    """
    global _patched
    
    print("🔍 DEBUG: apply_schema_patch() called")
    
    if _patched:
        print("⚠️  DEBUG: Schema patch already applied, skipping")
        logger.debug("Schema patch already applied, skipping")
        return
    
    try:
        from config.settings import settings as app_settings
        from livekit.agents.llm import utils
        from livekit.agents.inference import llm as inference_llm

        resolved_provider = str(provider_name or getattr(app_settings, "llm_provider", "") or "").strip().lower()
        force_loose_tool_schema = resolved_provider != "openai"
        logger.info(
            "schema_patch_provider provider=%s strict_tool_schema=%s",
            resolved_provider or "unknown",
            not force_loose_tool_schema,
        )
        
        print("🔍 DEBUG: Imported livekit.agents.llm.utils")
        
        # Store original functions
        _orig_build_legacy = utils.build_legacy_openai_schema
        _orig_build_strict = utils.build_strict_openai_schema
        
        print(f"🔍 DEBUG: Stored original functions: {_orig_build_legacy}, {_orig_build_strict}")
        
        def patched_build_legacy(function_tool, *, internally_tagged=False):
            """Patched version that ensures 'properties' exists."""
            result = _orig_build_legacy(function_tool, internally_tagged=internally_tagged)
            
            # Fix the parameters schema
            params_key = "parameters" if internally_tagged else "parameters"
            if internally_tagged:
                schema = result.get("parameters", {})
            else:
                schema = result.get("function", {}).get("parameters", {})
            
            # Ensure properties exists
            if "properties" not in schema:
                print(f"🔧 PATCH: Adding 'properties': {{}} to legacy tool '{function_tool.info.name}'")
                logger.debug(f"🔧 Adding 'properties': {{}} to tool '{function_tool.info.name}'")
                schema["properties"] = {}
            
            if internally_tagged:
                result["parameters"] = schema
            else:
                result["function"]["parameters"] = schema
            
            return result
        
        def patched_build_strict(function_tool):
            """Patched version that ensures 'properties' exists."""
            result = _orig_build_strict(function_tool)
            
            # Fix the parameters schema
            schema = result.get("function", {}).get("parameters", {})
            
            print(f"🔍 PATCH: Checking strict tool '{function_tool.info.name}' - has properties: {'properties' in schema}")
            logger.info(f"🔍 PATCH: Checking strict tool '{function_tool.info.name}' - has properties: {'properties' in schema}")
            
            # Ensure properties exists
            if "properties" not in schema:
                print(f"🔧 PATCH: Adding 'properties': {{}} to strict tool '{function_tool.info.name}'")
                logger.info(f"🔧 PATCH: Adding 'properties': {{}} to strict tool '{function_tool.info.name}'")
                schema["properties"] = {}
            
            result["function"]["parameters"] = schema
            print(f"🔍 PATCH: Final schema for '{function_tool.info.name}': {result}")
            logger.info(f"🔍 PATCH: Final schema for '{function_tool.info.name}': {result}")
            return result
        
        # Apply patches
        utils.build_legacy_openai_schema = patched_build_legacy
        utils.build_strict_openai_schema = patched_build_strict
        
        print("✅ DEBUG: Patched functions assigned to utils module")
        
        # Verify the patch is in place
        # Verify patch success
        is_patched = getattr(utils.build_strict_openai_schema, "is_patched_build_strict", False)
        logger.debug(f"🔍 DEBUG: Verifying patch - utils.build_strict_openai_schema is patched_build_strict: {is_patched}")
        
        # Also verify by checking the function object itself
        logger.debug(f"🔍 DEBUG: utils.build_strict_openai_schema = {utils.build_strict_openai_schema}")

        # Double check by importing from full path
        import livekit.agents.llm.utils as full_path_utils
        full_path_is_patched = getattr(full_path_utils.build_strict_openai_schema, "is_patched_build_strict", False)
        logger.debug(f"🔍 DEBUG: livekit.agents.llm.utils.build_strict_openai_schema is patched: {full_path_is_patched}")

        if force_loose_tool_schema:
            if not getattr(inference_llm.LLMStream, "_is_patched_init", False):
                _orig_stream_init = inference_llm.LLMStream.__init__

                def patched_stream_init(self, *args, **kwargs):
                    if "strict_tool_schema" in kwargs:
                        if kwargs["strict_tool_schema"]:
                            logger.warning(
                                "🔧 PATCH: Forcing strict_tool_schema=False for %s (was True)",
                                self.__class__.__name__,
                            )
                        kwargs["strict_tool_schema"] = False
                    return _orig_stream_init(self, *args, **kwargs)

                patched_stream_init._is_patched_init = True
                inference_llm.LLMStream.__init__ = patched_stream_init
                logger.info(
                    "✅ Applied LLMStream patch to force strict_tool_schema=False for provider=%s",
                    resolved_provider or "unknown",
                )
            else:
                logger.info("ℹ️ LLMStream already patched")
        else:
            logger.info("✅ OpenAI provider detected; preserving strict_tool_schema=True")

        _patched = True
        print("✅ Applied LiveKit schema patch for strict JSON Schema compliance")
        logger.info("✅ Applied LiveKit schema patch for strict JSON Schema compliance")
        
    except Exception as e:
        print(f"❌ DEBUG: Failed to apply schema patch: {e}")
        import traceback
        traceback.print_exc()
        logger.error(f"❌ Failed to apply schema patch: {e}")
        raise
