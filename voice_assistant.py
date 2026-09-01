"""
Simple Siri-like Voice Assistant
----------------------------------
Listens for a voice command, converts it to text (online first, offline
fallback), matches it against a command table, and executes an action
(usually launching an application).

SETUP
-----
1. Install dependencies:
   pip install SpeechRecognition vosk pyttsx3 sounddevice pyaudio

2. Download an offline Vosk model (needed for offline recognition):
   https://alphacephei.com/vosk/models
   e.g. "vosk-model-small-en-us-0.15" (~40MB, decent accuracy, low resource use)
   Unzip it and set VOSK_MODEL_PATH below to the folder path.

3. Edit the COMMANDS dict to match apps installed on your machine.

4. Run:
   python voice_assistant.py

Press Ctrl+C to quit. Say "exit" or "quit" to stop the assistant.
"""

import argparse
import json
import os
import platform
import queue
import subprocess
import sys

import speech_recognition as sr
import pyttsx3

# Offline recognition (Vosk) is optional — only imported if the model path exists,
# so the script still runs online-only if you skip the offline setup.
VOSK_MODEL_PATH = "vosk-model-small-en-us-0.15"  # <-- change to your model folder
OFFLINE_AVAILABLE = os.path.isdir(VOSK_MODEL_PATH)

if OFFLINE_AVAILABLE:
    import sounddevice as sd
    from vosk import Model, KaldiRecognizer

    _vosk_model = Model(VOSK_MODEL_PATH)


# --------------------------------------------------------------------------
# Text-to-speech (always offline, no API key needed)
# --------------------------------------------------------------------------
# Current setup (commented out):
# DEFAULT_ASSISTANT_NAME = "Assistant"
# CURRENT_ASSISTANT_NAME = DEFAULT_ASSISTANT_NAME
# tts_engine = pyttsx3.init()
# tts_engine.setProperty("rate", 175)

# Your custom setup:
# DEFAULT_ASSISTANT_NAME = "Nova"
DEFAULT_ASSISTANT_NAME = "Collins Akoja"
CURRENT_ASSISTANT_NAME = DEFAULT_ASSISTANT_NAME

tts_engine = pyttsx3.init()
tts_engine.setProperty("rate", 175)


def get_available_voices():
    voices = tts_engine.getProperty("voices") or []
    return [voice.name for voice in voices]


def set_assistant_name(name: str | None = None):
    global CURRENT_ASSISTANT_NAME
    chosen_name = (name or DEFAULT_ASSISTANT_NAME).strip()
    CURRENT_ASSISTANT_NAME = chosen_name or DEFAULT_ASSISTANT_NAME
    return CURRENT_ASSISTANT_NAME


def set_voice_by_name(voice_name: str | None = None, voice_index: int | None = None):
    voices = tts_engine.getProperty("voices")
    if not voices:
        return None

    if voice_name:
        for voice in voices:
            if voice.name.lower() == voice_name.lower():
                tts_engine.setProperty("voice", voice.id)
                return voice.name
        raise ValueError(f"Voice '{voice_name}' was not found. Available voices: {', '.join(v.name for v in voices)}")

    if voice_index is not None:
        if 0 <= voice_index < len(voices):
            tts_engine.setProperty("voice", voices[voice_index].id)
            return voices[voice_index].name
        raise IndexError(f"Voice index {voice_index} is out of range. Use 0 to {len(voices) - 1}.")

    return None


def configure_assistant(name: str | None = None, voice_name: str | None = None, voice_index: int | None = None):
    set_assistant_name(name)
    try:
        selected_voice = set_voice_by_name(voice_name=voice_name, voice_index=voice_index)
    except (ValueError, IndexError) as exc:
        print(f"[warning] {exc}")
        selected_voice = None
    return {
        "name": CURRENT_ASSISTANT_NAME,
        "voice": selected_voice,
    }


def speak(text: str):
    print(f"[{CURRENT_ASSISTANT_NAME}] {text}")
    tts_engine.say(text)
    tts_engine.runAndWait()


# --------------------------------------------------------------------------
# App launching (cross-platform)
# --------------------------------------------------------------------------
SYSTEM = platform.system()  # "Windows", "Darwin" (mac), "Linux"


def open_app(name: str, mac_bundle=None, linux_cmd=None, windows_cmd=None):
    """Launch an application by name, resolving per-OS launch command."""
    try:
        if SYSTEM == "Darwin":
            subprocess.Popen(["open", "-a", mac_bundle or name])
        elif SYSTEM == "Windows":
            command = windows_cmd or name
            if command.startswith("start "):
                os.system(command)
            else:
                os.system(f"start {command}")
        else:  # Linux
            subprocess.Popen([linux_cmd or name.lower()])
        return f"Opening {name}"
    except Exception as e:
        return f"Couldn't open {name}: {e}"


def close_app(name: str, mac_bundle=None, linux_cmd=None, windows_cmd=None):
    """Close an application by name, resolving per-OS shutdown command."""
    try:
        if SYSTEM == "Darwin":
            target = mac_bundle or name
            subprocess.Popen(["osascript", "-e", f'tell application "{target}" to quit'])
        elif SYSTEM == "Windows":
            command = windows_cmd or f"taskkill /F /IM {name.lower()}.exe"
            os.system(command)
        else:  # Linux
            if linux_cmd:
                subprocess.Popen(linux_cmd, shell=True)
            else:
                subprocess.Popen(["pkill", "-f", name.lower()])
        return f"Closing {name}"
    except Exception as e:
        return f"Couldn't close {name}: {e}"


def open_url(url: str, label: str):
    import webbrowser
    webbrowser.open(url)
    return f"Opening {label}"


def toggle_spotify_playback(action: str = "toggle"):
    """Control Spotify playback using OS commands."""
    if SYSTEM == "Windows":
        if action == "play":
            os.system("start spotify:play")
        elif action == "pause":
            os.system("start spotify:pause")
        else:
            os.system("start spotify:")
        return f"{action.capitalize()}ed Spotify"

    if SYSTEM == "Darwin":
        script = (
            "tell application \"Spotify\" to play"
            if action == "play"
            else "tell application \"Spotify\" to pause"
            if action == "pause"
            else "tell application \"Spotify\" to playpause"
        )
        subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"{action.capitalize()}ed Spotify"

    if action == "play":
        subprocess.Popen(["spotify", "play"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif action == "pause":
        subprocess.Popen(["spotify", "pause"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen(["spotify"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return f"{action.capitalize()}ed Spotify"


def skip_spotify_track(direction: str = "next"):
    """Skip to the next or previous Spotify track."""
    if SYSTEM == "Windows":
        if direction == "previous":
            os.system("start spotify:previous")
            return "Playing previous track"
        os.system("start spotify:next")
        return "Skipping track"

    if SYSTEM == "Darwin":
        script = "tell application \"Spotify\" to previous track" if direction == "previous" else "tell application \"Spotify\" to next track"
        subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "Skipping track" if direction != "previous" else "Playing previous track"

    if direction == "previous":
        subprocess.Popen(["spotify", "previous"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "Playing previous track"
    subprocess.Popen(["spotify", "next"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return "Skipping track"


def record_video():
    """Open the camera/video recorder as requested by voice command."""
    if SYSTEM == "Windows":
        os.system("start microsoft.windows.camera:")
        return "Recording video"
    if SYSTEM == "Darwin":
        subprocess.Popen(["open", "-a", "Photo Booth"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "Recording video"
    subprocess.Popen(["cheese"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return "Recording video"


def calculate_expression(text: str) -> str:
    """Parse simple arithmetic phrases and evaluate them."""
    cleaned = text.lower().replace("calculate", "").replace("what is", "").strip()
    cleaned = cleaned.replace("plus", "+").replace("minus", "-").replace("times", "*").replace("multiplied by", "*")
    cleaned = cleaned.replace("divided by", "/").replace("over", "/").replace("equals", "")

    # Keep only digits, operators, whitespace and decimal points
    sanitized = "".join(ch for ch in cleaned if ch.isdigit() or ch in "+-*/. ()")
    sanitized = sanitized.replace(" ", "")
    if not sanitized:
        return "Sorry, I couldn't understand that calculation."

    try:
        return str(eval(sanitized, {"__builtins__": {}}, {}))
    except Exception:
        return "Sorry, I couldn't calculate that."


# --------------------------------------------------------------------------
# Command table — map trigger phrases to actions.
# Add / edit entries to match the apps you actually have installed.
# --------------------------------------------------------------------------
COMMANDS = {
    "open browser": lambda: open_app("Google Chrome", mac_bundle="Google Chrome",
                                      linux_cmd="google-chrome", windows_cmd="chrome"),
    "open notepad": lambda: open_app("Notepad", mac_bundle="TextEdit",
                                      linux_cmd="gedit", windows_cmd="notepad"),
    "open calculator": lambda: open_app("Calculator", mac_bundle="Calculator",
                                         linux_cmd="gnome-calculator", windows_cmd="calc"),
    "open visual studio code": lambda: open_app("VS Code", mac_bundle="Visual Studio Code",
                                   linux_cmd="code", windows_cmd="code"),
    "open spotify": lambda: open_app("Spotify", mac_bundle="Spotify",
                                      linux_cmd="spotify", windows_cmd="spotify"),
    "play me a song on spotify": lambda: open_url("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM1", "Spotify Playlist"),
    "open WhatsApp": lambda: open_url("https://web.whatsapp.com", "WhatsApp"),
    "close WhatsApp": lambda: open_url("https://web.whatsapp.com", "WhatsApp"),
    "open youtube": lambda: open_url("https://youtube.com", "YouTube"),
    "what time is it": lambda: __import__("datetime").datetime.now().strftime(
        "It's %I:%M %p"),
    "open camera": lambda: open_app("Camera", mac_bundle="Photo Booth", windows_cmd="microsoft.windows.camera:", linux_cmd="cheese"),
    "open chatgpt": lambda: open_url("https://chat.openai.com", "ChatGPT"),
    "open gmail": lambda: open_url("https://mail.google.com", "Gmail"),
    "open google": lambda: open_url("https://www.google.com", "Google"),
    "close camera": lambda: close_app("Camera", mac_bundle="Photo Booth", windows_cmd="taskkill /F /IM WindowsCamera.exe", linux_cmd="pkill cheese"),
    "record video": lambda: record_video(),
    "play spotify": lambda: toggle_spotify_playback("play"),
    "pause spotify": lambda: toggle_spotify_playback("pause"),
    "play song": lambda: toggle_spotify_playback("play"),
    "pause song": lambda: toggle_spotify_playback("pause"),
    # "close browser": lambda: open_app("Google Chrome", mac_bundle="Google Chrome",
    #                                    linux_cmd="pkill chrome", windows_cmd="taskkill /IM chrome.exe"),
    # "close notepad": lambda: open_app("Notepad", mac_bundle="TextEdit",
    #                                    linux_cmd="pkill gedit", windows_cmd="taskkill /IM notepad.exe"),
    # "close calculator": lambda: open_app("Calculator", mac_bundle="Calculator",
    #                                       linux_cmd="pkill gnome-calculator", windows_cmd="taskkill /IM calc.exe"),
    # "close visual studio code": lambda: open_app("VS Code", mac_bundle="Visual Studio ",
                                    # linux_cmd="pkill code", windows_cmd="taskkill /IM code.exe"),
}

EXIT_WORDS = {"exit", "quit", "stop listening", "goodbye", "shutdown"}


def parse_and_run(text: str) -> bool:
    """Match recognized text to a command. Returns False if it's an exit command."""
    text = text.lower().strip()
    print(f"[heard] {text}")

    if any(word in text for word in EXIT_WORDS):
        speak(f"Goodbye, {CURRENT_ASSISTANT_NAME} is offline.")
        return False

    if text in {"hello", "hi", "hey", "good morning", "good afternoon", "good evening"}:
        speak("Hello! I am ready to help. Ask me to open apps, play music, do math, or tell you the time.")
        return True

    if "what can you do" in text or "what are your commands" in text or "list commands" in text or "help" in text:
        speak(
            "I can open apps, close apps, play or pause Spotify, skip songs, do quick math, record video, "
            "open the camera, tell the time and date, and answer simple commands."
        )
        return True

    if "what date is it" in text or "what's the date" in text or "date is it" in text:
        speak(__import__("datetime").datetime.now().strftime("Today's date is %A, %B %d, %Y"))
        return True

    if "what time is it" in text or "time is it" in text:
        speak(__import__("datetime").datetime.now().strftime("It's %I:%M %p"))
        return True

    if text.startswith("close "):
        target = text[len("close "):].strip()
        if target:
            result = close_app(target)
            speak(result)
            return True

    if text.startswith("open ") or text.startswith("launch "):
        target = text[len("open "):] if text.startswith("open ") else text[len("launch "):]
        target = target.strip()
        if target:
            result = open_app(target.title() if target.lower() != "browser" else "Google Chrome")
            speak(result)
            return True

    if "resume spotify" in text or "continue spotify" in text or "play spotify" in text or "play song" in text or "resume song" in text:
        result = toggle_spotify_playback("play")
        speak(result)
        return True

    if "pause spotify" in text or "pause song" in text or "stop spotify" in text or "stop song" in text:
        result = toggle_spotify_playback("pause")
        speak(result)
        return True

    if "next song" in text or "skip song" in text or "next track" in text:
        result = skip_spotify_track("next")
        speak(result)
        return True

    if "previous song" in text or "last song" in text or "previous track" in text:
        result = skip_spotify_track("previous")
        speak(result)
        return True

    if "calculate" in text or "what is" in text and any(op in text for op in ["plus", "minus", "times", "divided", "multiplied", "+", "-", "*", "/"]):
        result = calculate_expression(text)
        speak(result)
        return True

    if "record video" in text or "record a video" in text or "start recording" in text:
        result = record_video()
        speak(result)
        return True

    if "open camera" in text or "camera" in text and ("open" in text or "launch" in text):
        result = open_app("Camera", mac_bundle="Photo Booth", windows_cmd="microsoft.windows.camera:", linux_cmd="cheese")
        speak(result)
        return True

    for phrase, action in COMMANDS.items():
        if phrase in text:
            result = action()
            speak(result)
            return True

    speak("Sorry, I didn't recognize that command")
    return True


# --------------------------------------------------------------------------
# Speech recognition — online first, offline fallback
# --------------------------------------------------------------------------
recognizer = sr.Recognizer()
mic = sr.Microphone()


def listen_online(audio) -> str | None:
    try:
        return recognizer.recognize_google(audio)
    except (sr.UnknownValueError, sr.RequestError):
        return None


def listen_offline_from_audio(audio) -> str | None:
    """Fallback offline recognition using Vosk on the same captured audio."""
    if not OFFLINE_AVAILABLE:
        return None
    raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
    rec = KaldiRecognizer(_vosk_model, 16000)
    rec.AcceptWaveform(raw)
    result = json.loads(rec.FinalResult())
    return result.get("text") or None


def capture_and_transcribe() -> str | None:
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        print("[listening]...")
        audio = recognizer.listen(source, timeout=6, phrase_time_limit=6)

    text = listen_online(audio)
    if text:
        return text

    print("[online recognition failed or offline — trying offline model]")
    return listen_offline_from_audio(audio)


# --------------------------------------------------------------------------
# Main loop
# --------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Voice assistant")
    parser.add_argument("--name", default=DEFAULT_ASSISTANT_NAME, help="Set the assistant name, for example --name Jarvis")
    parser.add_argument("--voice", help="Set the speaking voice by name, for example --voice \"Microsoft Zira Desktop\"")
    parser.add_argument("--voice-index", type=int, help="Set the speaking voice by index number")
    parser.add_argument("--list-voices", action="store_true", help="List all available Windows voices and exit")
    args = parser.parse_args()

    if args.list_voices:
        voices = get_available_voices()
        if not voices:
            print("No TTS voices were detected on this system.")
            return
        print("Available voices:")
        for index, voice in enumerate(voices):
            print(f"  {index}: {voice}")
        return

    config = configure_assistant(
        name=args.name,
        voice_name=args.voice,
        voice_index=args.voice_index,
    )
    speak(f"{config['name']} ready. Say a command.")
    if not OFFLINE_AVAILABLE:
        print("NOTE: offline model not found at "
              f"'{VOSK_MODEL_PATH}' — offline fallback is disabled. "
              "Download a Vosk model to enable it.")

    running = True
    while running:
        try:
            text = capture_and_transcribe()
        except sr.WaitTimeoutError:
            continue
        except KeyboardInterrupt:
            break

        if not text:
            print("[no speech detected]")
            continue

        running = parse_and_run(text)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(0)
