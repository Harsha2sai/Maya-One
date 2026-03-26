# scripts/llm_probe.py
import os, sys, json, time
from dotenv import load_dotenv

load_dotenv()

def probe_openai():
    try:
        import openai
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("openai: skipped (no key)")
            return False
            
        openai.api_key = api_key
        # Check if new client format needed (openai>=1.0.0)
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            r = client.chat.completions.create(
                model="gpt-4o-mini", 
                messages=[{"role":"system","content":"probe"},{"role":"user","content":"ping"}], 
                max_tokens=1
            )
            print("openai: ok (v1)", r.usage)
        except ImportError:
            r = openai.ChatCompletion.create(model="gpt-4o-mini", messages=[{"role":"system","content":"probe"},{"role":"user","content":"ping"}], max_tokens=1)
            print("openai: ok (legacy)", r['usage'])
        return True
    except Exception as e:
        print("openai_error", str(e))
        return False

def probe_groq():
    try:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            print("groq: skipped (no key)")
            return False

        from groq import Groq
        client = Groq(api_key=api_key)
        r = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role":"user","content":"ping"}],
            max_tokens=1
        )
        print("groq: ok", r.usage)
        return True
    except Exception as e:
        print("groq_error", str(e))
        return False

if __name__=="__main__":
    ok = probe_openai() or probe_groq()
    print("OK" if ok else "FAILED")
    sys.exit(0 if ok else 2)
