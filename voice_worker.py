"""Converts speech into Zyraena's voice. Runs inside Wichelberg's Python, not Zyraena's.

Wichelberg (the user's voice changer) has the RVC voice packs, ONNX Runtime and
the conversion code; this script reuses its offline AI path (render_ai: high-pass,
gate, auto level, RVC with automatic pitch shift to the voice's target, silence
mask) instead of duplicating it. Started and kept alive by voice.py.

argv: <wichelberg _wichelberg dir> <voice id>
stdin: one JSON request per line: {"in": audio path, "wav": out path, "ogg": out path or null}
stdout: {"ready": true} once loaded, then one JSON reply per request:
        {"ok": true, "seconds": ...} or {"ok": false, "error": "..."}
"""
import json
import sys
import time
from pathlib import Path

SAMPLE_RATE = 48000  # Wichelberg's engines take and return 48 kHz mono float32


def main():
    wichelberg, voice_id = Path(sys.argv[1]), sys.argv[2]
    sys.path.insert(0, str(wichelberg))

    import soundfile as sf
    from voicechanger.ai.base import ConvertParams
    from voicechanger.ai.rvc_onnx import resample
    from voicechanger.ai.voices import load_voice
    from voicechanger.dsp.params import VoiceSettings
    from voicechanger.render import render_ai

    voice = load_voice(wichelberg / "models" / "voices" / voice_id)
    settings = VoiceSettings()
    params = ConvertParams(index_rate=voice.default_index_rate)
    print(json.dumps({"ready": True}), flush=True)

    for line in sys.stdin:
        if not line.strip():
            continue
        started = time.perf_counter()
        try:
            request = json.loads(line)
            audio, rate = sf.read(request["in"], dtype="float32", always_2d=True)
            audio = audio.mean(axis=1)
            if rate != SAMPLE_RATE:
                audio = resample(audio, rate, SAMPLE_RATE)
            converted, _, _, _ = render_ai(audio, settings, voice, 0.0, params)
            sf.write(request["wav"], converted, SAMPLE_RATE, subtype="PCM_16")
            if request.get("ogg"):
                sf.write(request["ogg"], converted, SAMPLE_RATE, format="OGG", subtype="OPUS")
            reply = {"ok": True, "seconds": round(time.perf_counter() - started, 2)}
        except Exception as e:
            reply = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        print(json.dumps(reply), flush=True)


if __name__ == "__main__":
    main()
