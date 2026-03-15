import os
import json
import subprocess
import openai
import re
import argparse
from typing import List
from openai import OpenAI
import sounddevice as sd
from faster_whisper import WhisperModel
from kittentts import KittenTTS
from huggingface_hub import hf_hub_download

# --- CONFIG ---
WIKI_DIR = "./minecraft_markdown_pages"

# --- TOOL: RIPGREP ---
def search_wiki(query: str):
    print(f"🔍 Searching wiki for: '{query}'...")
    try:
        # Use -l to get filenames or -C for snippets
        cmd = ["rg", "-i", "-C", "2", "-m", "3", "--heading", query, WIKI_DIR]
        result = subprocess.run(cmd, capture_output=True, text=True)
        output = result.stdout if result.stdout else "No matches found."
        print(f"Search results:\n{output}")
        return output
    except Exception as e:
        return f"Search error: {str(e)}"
    
def listen(stt_model):
    """Record 5 seconds of audio and transcribe."""
    fs = 16000
    print("👂 Listening...")
    duration = 5 
    recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='float32')
    sd.wait()
    segments, _ = stt_model.transcribe(recording.flatten())
    return " ".join([s.text for s in segments]).strip()

# --- AGENT LOGIC ---
def run_agent_loop(args):
    # Initialize models
    client = OpenAI(base_url=args.server_url, api_key="lm-studio")
    stt_model = WhisperModel(args.stt_model, device="cpu", compute_type="int8")
    
    # Resolve TTS paths
    tts_model_path = args.tts_model_path
    if not tts_model_path:
        tts_model_path = hf_hub_download(args.tts_repo, args.tts_model_file)
    
    tts_voices_path = args.tts_voices_path
    if not tts_voices_path:
        tts_voices_path = hf_hub_download(args.tts_repo, args.tts_voices_file)
        
    tts_model = KittenTTS(model_path=tts_model_path, voices_path=tts_voices_path)

    # Base system prompt
    system_prompt = {"role": "system", "content": "You are a local assistant for Minecraft. Use the search_wiki tool to find information. Give very short answers, no markdown, and optionally suggest followups."}
    
    # Define tool for OpenAI format
    tools = [{
        "type": "function",
        "function": {
            "name": "search_wiki",
            "description": "Search the minecraft wiki",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                },
                "required": ["query"]
            }
        }
    }]

    first_run = True
    while True:
        if first_run and args.message:
            user_input = args.message
            first_run = False
        else:
            input("\n[Press Enter to Speak]")
            user_input = listen(stt_model)
            if not user_input: continue
        
        print(f"👤 User: {user_input}")
        
        # Reset messages for each turn to avoid context bloat and role errors
        messages = [system_prompt, {"role": "user", "content": user_input}]

        while True:
            # The API call
            try:
                response = client.chat.completions.create(
                    model=args.llm_model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto"
                )
            except Exception as e:
                print(f"API Error: {e}")
                break
            
            msg = response.choices[0].message
            
            # If the model wants to talk to the user, exit tool loop
            if not msg.tool_calls:
                final_text = msg.content or ""
                break
            
            # Convert assistant message to dict and ensure content is a string
            assistant_msg = msg.model_dump()
            if assistant_msg.get("content") is None:
                assistant_msg["content"] = ""
            messages.append(assistant_msg)
            
            for tool_call in msg.tool_calls:
                query = json.loads(tool_call.function.arguments).get("query")
                result = search_wiki(query)
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": "search_wiki",
                    "content": str(result)
                })

        # SPEAK
        print(f"🎙️ Agent: {final_text}")
        
        if args.speak:
            # Clean think tags
            clean_text = re.sub(r"<think>.*?</think>", "", final_text, flags=re.DOTALL).strip()
            
            # Split into sentences or chunks for TTS
            sentences = re.split(r'(?<=[.!?]) +', clean_text)
            for sentence in sentences:
                if not sentence.strip(): continue
                try:
                    audio = tts_model.generate(sentence, voice=args.tts_voice, speed=2)
                    sd.play(audio, 24000)
                    sd.wait()
                except Exception as e:
                    print(f"TTS error on sentence: {sentence[:30]}... -> {e}")

        if args.message and not first_run:
            # Exit after processing the initial message if one was provided
            break

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Minecraft Wiki Chatbot")
    parser.add_argument("--llm-model", type=str, default="qwen/qwen3.5-9b", help="LLM model name")
    parser.add_argument("--stt-model", type=str, default="base.en", help="Whisper model name")
    parser.add_argument("--tts-voice", type=str, default="expr-voice-2-f", help="TTS voice name")
    parser.add_argument("--tts-model-path", type=str, help="Local path to KittenTTS model (overrides HF)")
    parser.add_argument("--tts-voices-path", type=str, help="Local path to KittenTTS voices (overrides HF)")
    parser.add_argument("--tts-repo", type=str, default="KittenML/kitten-tts-nano-0.1", help="HF repo for TTS")
    parser.add_argument("--tts-model-file", type=str, default="kitten_tts_nano_v0_1.onnx", help="Model file in HF repo")
    parser.add_argument("--tts-voices-file", type=str, default="voices.npz", help="Voices file in HF repo")
    parser.add_argument("--server-url", type=str, default="http://192.168.1.31:1234/v1", help="LLM server URL")
    parser.add_argument("--message", type=str, help="Initial message to process")
    parser.add_argument("--speak", action=argparse.BooleanOptionalAction, default=True, help="Whether to speak the output")
    
    args = parser.parse_args()
    run_agent_loop(args)
