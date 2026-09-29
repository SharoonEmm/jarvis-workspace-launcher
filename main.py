import sounddevice as sd
import numpy as np
import speech_recognition as sr
import edge_tts
import pygame

import asyncio
import tempfile
import threading
import subprocess
import webbrowser
import os
import time

from pathlib import Path

import win32gui
import win32api


# =========================================================
# SETTINGS
# =========================================================

# Microphone audio settings. Increase CLAP_THRESHOLD if ordinary noise triggers it;
# decrease it if JARVIS misses your clap. The detector currently uses peak volume.
SAMPLE_RATE = 44100
BLOCK_SIZE = 2205
CLAP_THRESHOLD = 0.6

# Change these values for your own Windows workspace before running.
CHATGPT_URL = "https://chatgpt.com"
SPOTIFY_URI = "spotify:"
VSCODE_SHORTCUT = Path.home() / "Desktop" / "Visual Studio Code.lnk"

# Window titles are partial, case-insensitive matches. Browser tab titles may
# vary, so adjust these if a window is not found on your computer.
SPOTIFY_WINDOW_TITLE = "Spotify"
VSCODE_WINDOW_TITLE = "Visual Studio Code"
CHATGPT_WINDOW_TITLE = "ChatGPT"

# Fractions of the primary monitor's usable width. ChatGPT gets the remainder.
SPOTIFY_WIDTH_FRACTION = 0.10
VSCODE_WIDTH_FRACTION = 0.50

# Words required in the recognized phrase, regardless of order.
WAKE_WORDS = ("wake up", "daddy", "home")
GREETING = "Welcome home, sir. Systems online. Workspace ready."


# =========================================================
# JARVIS VOICE SETTINGS
# =========================================================

JARVIS_VOICE = "en-GB-RyanNeural"

# Snappy delivery
VOICE_RATE = "+7%"

# Slightly deeper voice
VOICE_PITCH = "-12Hz"

VOICE_VOLUME = "+0%"


# =========================================================
# AUDIO WAKE-UP SETTINGS
# =========================================================

# How long to wake the audio device before JARVIS speaks
AUDIO_PREWARM_SECONDS = 1.2

# Strength of the almost-silent wake-up tone
AUDIO_PREWARM_VOLUME = 300


# =========================================================
# CLAP DETECTION
# =========================================================

def wait_for_clap():

    # Listen until a single input block exceeds the peak-volume threshold.
    print("JARVIS is waiting... 👂")

    with sd.InputStream(
        channels=1,
        samplerate=SAMPLE_RATE,
        blocksize=BLOCK_SIZE
    ) as stream:

        while True:

            audio, overflowed = stream.read(BLOCK_SIZE)

            volume = np.max(
                np.abs(audio)
            )

            if volume > CLAP_THRESHOLD:

                print("\n👏 CLAP DETECTED")

                return


# =========================================================
# VOICE RECOGNITION
# =========================================================

def listen_for_command():

    print("🎙️ Listening for command...")

    # Record a fixed four-second clip after the clap.
    duration = 4

    recording = sd.rec(
        int(duration * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32"
    )

    sd.wait()

    # Convert microphone recording to 16-bit PCM
    audio_int16 = (
        recording * 32767
    ).astype(np.int16)

    audio_data = sr.AudioData(
        audio_int16.tobytes(),
        SAMPLE_RATE,
        2
    )

    recognizer = sr.Recognizer()

    try:

        text = recognizer.recognize_google(
            audio_data
        )

        print(
            f'You said: "{text}"'
        )

        return text.lower()

    except sr.UnknownValueError:

        print(
            "JARVIS couldn't understand you."
        )

        return ""

    except sr.RequestError as error:

        print(
            "Speech recognition error:",
            error
        )

        return ""


# =========================================================
# AUDIO PRE-WARM
# =========================================================

def prewarm_audio():

    # Play a barely audible tone to wake slow HDMI/Bluetooth audio output.
    duration = AUDIO_PREWARM_SECONDS

    samples = int(
        SAMPLE_RATE * duration
    )

    t = (
        np.arange(samples)
        / SAMPLE_RATE
    )

    # Very quiet 100 Hz tone.
    #
    # This is intentionally non-zero audio because some
    # HDMI / monitor / Bluetooth audio devices ignore
    # pure digital silence and stay asleep.
    tone = (
        np.sin(
            2 * np.pi * 100 * t
        )
        * AUDIO_PREWARM_VOLUME
    ).astype(np.int16)

    stereo = np.column_stack(
        (
            tone,
            tone
        )
    )

    warmup_sound = pygame.sndarray.make_sound(
        stereo
    )

    channel = warmup_sound.play()

    if channel is not None:

        while channel.get_busy():

            time.sleep(
                0.01
            )


# =========================================================
# JARVIS NEURAL VOICE
# =========================================================

def speak(text):
    """Generate speech online and play it while app windows are launched."""

    def voice_worker():

        temporary_file = tempfile.NamedTemporaryFile(
            suffix=".mp3",
            delete=False
        )

        audio_path = Path(
            temporary_file.name
        )

        temporary_file.close()


        # -------------------------------------------------
        # GENERATE EDGE TTS AUDIO
        # -------------------------------------------------

        async def generate_voice():

            communicate = edge_tts.Communicate(
                text=text,
                voice=JARVIS_VOICE,
                rate=VOICE_RATE,
                pitch=VOICE_PITCH,
                volume=VOICE_VOLUME
            )

            await communicate.save(
                str(audio_path)
            )


        try:

            print(
                "🔊 Generating JARVIS voice..."
            )

            asyncio.run(
                generate_voice()
            )


            # =================================================
            # INITIALIZE AUDIO
            # =================================================

            if pygame.mixer.get_init():

                pygame.mixer.quit()


            pygame.mixer.init(
                frequency=SAMPLE_RATE,
                size=-16,
                channels=2,
                buffer=512
            )


            # =================================================
            # LOAD SPEECH BEFORE WAKING AUDIO
            # =================================================

            pygame.mixer.music.load(
                str(audio_path)
            )

            pygame.mixer.music.set_volume(
                1.0
            )


            # =================================================
            # WAKE SPEAKERS / AUDIO OUTPUT
            # =================================================

            print(
                "🔊 Waking audio device..."
            )

            prewarm_audio()


            # =================================================
            # PLAY JARVIS
            # =================================================

            print(
                "🔊 JARVIS speaking..."
            )

            pygame.mixer.music.play()


            while pygame.mixer.music.get_busy():

                time.sleep(
                    0.05
                )


            pygame.mixer.music.stop()


            try:

                pygame.mixer.music.unload()

            except Exception:

                pass


            print(
                "✅ JARVIS voice complete"
            )


        except Exception as error:

            print(
                "❌ Voice error:",
                error
            )


        finally:

            # =================================================
            # CLOSE AUDIO SYSTEM
            # =================================================

            try:

                if pygame.mixer.get_init():

                    pygame.mixer.quit()

            except Exception:

                pass


            # =================================================
            # DELETE TEMPORARY MP3
            # =================================================

            try:

                audio_path.unlink()

            except OSError:

                pass


    # Non-daemon thread:
    # Python will not kill JARVIS while he's speaking.
    voice_thread = threading.Thread(
        target=voice_worker
    )

    voice_thread.start()

    return voice_thread


# =========================================================
# LAUNCH APPLICATIONS
# =========================================================

def launch_apps():

    print(
        "⚡ Initializing workspace..."
    )


    # =====================================================
    # CHATGPT
    # =====================================================

    try:

        webbrowser.open(
            CHATGPT_URL
        )

        print(
            "✅ ChatGPT launching"
        )

    except Exception as error:

        print(
            "❌ Couldn't open ChatGPT:",
            error
        )


    # =====================================================
    # SPOTIFY
    # =====================================================

    try:

        subprocess.Popen(
            [
                "cmd",
                "/c",
                "start",
                "",
                SPOTIFY_URI
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        print(
            "✅ Spotify launching"
        )

    except Exception as error:

        print(
            "❌ Couldn't open Spotify:",
            error
        )


    # =====================================================
    # VS CODE
    # =====================================================

    try:

        os.startfile(
            str(VSCODE_SHORTCUT)
        )

        print(
            "✅ VS Code launching"
        )

    except Exception as error:

        print(
            "❌ Couldn't open VS Code:",
            error
        )


# =========================================================
# WINDOW ARRANGEMENT
# =========================================================

def arrange_windows():
    """Place the three app windows across the primary monitor work area."""

    print(
        "🖥️ Preparing workspace layout..."
    )

    monitors = win32api.EnumDisplayMonitors()

    primary_monitor = None


    # =====================================================
    # FIND PRIMARY MONITOR
    # =====================================================

    for monitor in monitors:

        handle = monitor[0]

        info = win32api.GetMonitorInfo(
            handle
        )

        if info["Flags"] == 1:

            (
                work_left,
                work_top,
                work_right,
                work_bottom
            ) = info["Work"]

            primary_monitor = {

                "left":
                    work_left,

                "top":
                    work_top,

                "width":
                    work_right
                    - work_left,

                "height":
                    work_bottom
                    - work_top
            }

            break


    if primary_monitor is None:

        print(
            "❌ Couldn't detect primary monitor."
        )

        return


    left = primary_monitor["left"]
    top = primary_monitor["top"]
    width = primary_monitor["width"]
    height = primary_monitor["height"]


    print(
        f"🎯 Main monitor: "
        f"{width}x{height} "
        f"at ({left}, {top})"
    )


    # =====================================================
    # WINDOW WIDTHS
    # =====================================================

    # Spotify gets the configured share of the primary display.
    spotify_width = int(
        width * SPOTIFY_WIDTH_FRACTION
    )

    # VS Code gets the configured share.
    vscode_width = int(
        width * VSCODE_WIDTH_FRACTION
    )

    # ChatGPT fills the remaining width.
    chatgpt_width = (
        width
        - spotify_width
        - vscode_width
    )


    # =====================================================
    # WINDOW WATCHER
    # =====================================================

    def watch_and_move(
        title_keyword,
        x,
        y,
        window_width,
        window_height
    ):

        # Poll for up to roughly ten seconds while apps open.
        for attempt in range(200):

            found_window = None


            def callback(hwnd, extra):

                nonlocal found_window


                if not win32gui.IsWindowVisible(
                    hwnd
                ):

                    return


                title = win32gui.GetWindowText(
                    hwnd
                )


                if (
                    title_keyword.lower()
                    in title.lower()
                ):

                    found_window = hwnd


            win32gui.EnumWindows(
                callback,
                None
            )


            # -------------------------------------------------
            # WINDOW FOUND
            # -------------------------------------------------

            if found_window:

                actual_title = win32gui.GetWindowText(
                    found_window
                )

                print(
                    f"✅ Found: "
                    f"{actual_title}"
                )


                # Restore from minimized/maximized state
                win32gui.ShowWindow(
                    found_window,
                    9
                )


                # Move and resize
                win32gui.MoveWindow(
                    found_window,
                    x,
                    y,
                    window_width,
                    window_height,
                    True
                )


                print(
                    f"📐 Positioned "
                    f"{title_keyword}"
                )

                return True


            time.sleep(
                0.05
            )


        print(
            f"⚠️ Couldn't find "
            f"{title_keyword}"
        )

        return False


    # =====================================================
    # SPOTIFY — LEFT 10%
    # =====================================================

    spotify_thread = threading.Thread(
        target=watch_and_move,
        args=(
            SPOTIFY_WINDOW_TITLE,
            left,
            top,
            spotify_width,
            height
        )
    )


    # =====================================================
    # VS CODE — MIDDLE 50%
    # =====================================================

    vscode_thread = threading.Thread(
        target=watch_and_move,
        args=(
            VSCODE_WINDOW_TITLE,
            left + spotify_width,
            top,
            vscode_width,
            height
        )
    )


    # =====================================================
    # CHATGPT — RIGHT 40%
    # =====================================================

    chatgpt_thread = threading.Thread(
        target=watch_and_move,
        args=(
            CHATGPT_WINDOW_TITLE,

            left
            + spotify_width
            + vscode_width,

            top,

            chatgpt_width,

            height
        )
    )


    # =====================================================
    # START ALL WATCHERS
    # =====================================================

    spotify_thread.start()

    vscode_thread.start()

    chatgpt_thread.start()


    # =====================================================
    # WAIT UNTIL WINDOWS ARE POSITIONED
    # =====================================================

    spotify_thread.join()

    vscode_thread.join()

    chatgpt_thread.join()


    print(
        "\n✅ Workspace configuration complete."
    )


# =========================================================
# WAKE JARVIS
# =========================================================

def wake_jarvis():

    print(
        "\n🔥 WAKE COMMAND ACCEPTED"
    )


    # =====================================================
    # JARVIS RESPONSE
    # =====================================================

    voice_thread = speak(GREETING)


    # =====================================================
    # LAUNCH APPLICATIONS
    # =====================================================

    launch_apps()


    # =====================================================
    # ARRANGE WINDOWS
    # =====================================================

    arrange_windows()


    # =====================================================
    # MAKE SURE VOICE FINISHES
    # =====================================================

    if voice_thread is not None:

        voice_thread.join(
            timeout=30
        )


# =========================================================
# MAIN PROGRAM
# =========================================================

if __name__ == "__main__":

    wait_for_clap()


    # Prevent clap from entering speech recognition
    time.sleep(
        0.4
    )


    command = listen_for_command()


    # =====================================================
    # CHECK WAKE PHRASE
    # =====================================================

    if all(word in command for word in WAKE_WORDS):

        wake_jarvis()


    else:

        print(
            "\n❌ Command rejected."
        )