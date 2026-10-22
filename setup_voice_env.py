"""Sets up local speech-to-text: python setup_voice_env.py [--test audio_file] [--training]

Creates voice_env (paths.voice_home()/env): a small venv whose own site-packages hold
only faster-whisper and ctranslate2. Everything else (numpy, onnxruntime, tokenizers,
huggingface_hub, av, and the CUDA DLLs that ship with torch) is read from Wichelberg's
training venv through a .pth file, so nothing big is downloaded twice. That venv is
never changed: packages go in with --no-deps, so pip can't upgrade or remove its
pinned versions (RVC training needs them).

Then it downloads the Whisper model (ZYRAENA_STT_MODEL; Zyraena itself never downloads
one) and starts speech_worker.py once to check it loads (and on which device). Safe to
run again, e.g. after changing ZYRAENA_STT_MODEL.

--training instead makes train_env (paths.voice_home()/train_env) the same way, for
train_stt.py: peft, accelerate and ctranslate2 (its model converter), so the runtime
voice_env stays small.

.env: ZYRAENA_TORCH_VENV (default Documents\\Projects\\Wichelberg_VoiceChanger\\data\\egitim\\venv),
      ZYRAENA_VOICE_HOME, ZYRAENA_STT_MODEL, ZYRAENA_STT_LANGUAGE.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

import paths

PACKAGES = ["faster-whisper==1.2.1", "ctranslate2==4.8.3"]
# The releases from the time of the training venv's transformers 4.49 / torch 2.7.
TRAINING_PACKAGES = ["peft==0.15.2", "accelerate==1.6.0", "ctranslate2==4.8.3"]
PTH_NAME = "wichelberg_egitim.pth"


def torch_venv():
    custom = os.environ.get("ZYRAENA_TORCH_VENV", "").strip()
    return Path(custom) if custom else (
        Path.home() / "Documents" / "Projects" / "Wichelberg_VoiceChanger" / "data" / "egitim" / "venv")


def read_cfg(venv):
    cfg = {}
    for line in (venv / "pyvenv.cfg").read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        cfg[key.strip()] = value.strip()
    return cfg


def make_overlay(env, packages):
    """A venv at `env` with `packages` of its own on top of the torch venv's. Returns its python."""
    source = torch_venv()
    source_packages = source / "Lib" / "site-packages"
    if not (source_packages / "torch").is_dir():
        sys.exit(f"No torch in {source_packages}. Set ZYRAENA_TORCH_VENV to a venv that has it.")
    cfg = read_cfg(source)
    base_python = Path(cfg["home"]) / "python.exe"
    if not base_python.is_file():
        sys.exit(f"{source} was made with {base_python}, which no longer exists.")

    python = env / "Scripts" / "python.exe"
    if not python.is_file():
        print(f"Creating {env} with Python {cfg.get('version')} ...")
        subprocess.run([str(base_python), "-m", "venv", str(env)], check=True)
    # Lines in a .pth go after the venv's own site-packages, so its packages win.
    (env / "Lib" / "site-packages" / PTH_NAME).write_text(str(source_packages) + "\n", encoding="utf-8")

    print("Installing", ", ".join(packages), "...")
    subprocess.run([str(python), "-m", "pip", "install", "--no-deps", "--disable-pip-version-check", *packages],
                   check=True)
    return python


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--test", help="an audio file to transcribe after setup")
    parser.add_argument("--training", action="store_true", help="make train_env for train_stt.py instead")
    args = parser.parse_args()

    if args.training:
        python = make_overlay(paths.voice_home() / "train_env", TRAINING_PACKAGES)
        print(f"Done. Run training with: {python} train_stt.py --help")
        return

    python = make_overlay(paths.voice_home() / "env", PACKAGES)

    os.environ["ZYRAENA_STT_PYTHON"] = str(python)
    import voice  # after the env exists: it looks for voice_env when used

    model = voice.local_stt.model_name()
    print(f"Getting the Whisper model {model} (the first time it downloads ~1.6 GB) ...")
    subprocess.run([str(python), "-I", str(paths.resource_dir() / "speech_worker.py"), "--download",
                    str(paths.voice_home() / "models"), model], check=True)
    print("Loading it ...")
    voice.local_stt.start()
    print(f"Ready on {voice.local_stt.device} in {voice.local_stt.load_seconds} s.")
    if args.test:
        text = voice.local_stt.transcribe(voice.to_wav_bytes(Path(args.test).read_bytes()))
        print(f"Heard: {text}")
    voice.local_stt.stop()
    print(f"Done. Python for speech: {python}")


if __name__ == "__main__":
    main()
