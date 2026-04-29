"""
VOXA Backend — Speech-to-Text Service (Layer 3: Speech Processing)
Prioritizes fine-tuned LoRA models, falls back to faster-whisper.
"""

import os
import logging
import tempfile
from pathlib import Path
from config import WHISPER_MODEL

logger = logging.getLogger("voxa.stt")

# -- CONFIG --
def get_device():
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"

DEVICE = get_device()
# Path to fine-tuned model (relative to project root)
LORA_ADAPTER_DIR = Path(__file__).resolve().parents[2] / "whisper_training" / "output" / "whisper-lora-automotive"
BASE_MODEL_ID = "openai/whisper-small"

# Lazy-loaded globals
_stt_type = None  # "transformers" or "faster_whisper"
_model = None
_processor = None


def init_stt_service(model_size: str = "base.en"):
    """
    Initialize the STT model. Prioritizes the fine-tuned LoRA model.
    """
    global _stt_type, _model, _processor

    if _model is not None:
        return

    # 1. Try to load fine-tuned LoRA model
    if LORA_ADAPTER_DIR.exists():
        logger.info(f"🚀 Loading FINE-TUNED model from {LORA_ADAPTER_DIR}...")
        try:
            from transformers import WhisperForConditionalGeneration, WhisperProcessor
            from peft import PeftModel
            
            _processor = WhisperProcessor.from_pretrained(BASE_MODEL_ID)
            base_model = WhisperForConditionalGeneration.from_pretrained(BASE_MODEL_ID)
            _model = PeftModel.from_pretrained(base_model, str(LORA_ADAPTER_DIR))
            _model.to(DEVICE).eval()
            
            _stt_type = "transformers"
            logger.info("Fine-tuned LoRA model loaded successfully")
            return
        except Exception as e:
            logger.error(f"Failed to load fine-tuned model: {e}. Falling back to faster-whisper.")

    # 2. Fallback to faster-whisper
    logger.info(f"⚠️ Using base faster-whisper ({model_size})...")
    try:
        from faster_whisper import WhisperModel
        _model = WhisperModel(
            model_size,
            device=DEVICE,
            compute_type="int8" if DEVICE == "cpu" else "float16",
            cpu_threads=os.cpu_count() or 4
        )
        _stt_type = "faster_whisper"
        logger.info(f"Faster-whisper '{model_size}' loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load faster-whisper: {e}")
        raise


async def transcribe_audio(audio_bytes: bytes, filename: str = "recording.webm") -> dict:
    """
    Transcribe audio bytes using the active model.
    """
    global _stt_type, _model, _processor

    if _model is None:
        init_stt_service(WHISPER_MODEL)

    suffix = Path(filename).suffix or ".webm"
    tmp_path = None
    wav_path = None

    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        # Convert to WAV/16k mono (Required for both models)
        from pydub import AudioSegment
        audio = AudioSegment.from_file(tmp_path)
        audio = audio.set_frame_rate(16000).set_channels(1)
        
        wav_path = tmp_path + ".wav"
        audio.export(wav_path, format="wav")

        if _stt_type == "transformers":
            import torch
            # Load with librosa to get numpy array
            import librosa
            audio_np, _ = librosa.load(wav_path, sr=16000)
            
            input_features = _processor.feature_extractor(
                audio_np, sampling_rate=16000, return_tensors="pt"
            ).input_features.to(DEVICE)

            with torch.no_grad():
                predicted_ids = _model.generate(input_features)
            
            text = _processor.tokenizer.batch_decode(predicted_ids, skip_special_tokens=True)[0].strip()
            confidence = 0.9  # Transformers doesn't give a simple confidence score easily
            language = "en"

        else:
            # faster-whisper logic
            segments, info = _model.transcribe(wav_path, language="en", beam_size=5, vad_filter=True)
            text = " ".join([seg.text.strip() for seg in segments]).strip()
            
            # Avg confidence from log probabilities
            import math
            probs = [math.exp(seg.avg_log_prob) for seg in segments]
            confidence = round(sum(probs) / len(probs), 3) if probs else 0.0
            language = info.language

        if not text:
            logger.warning("STT returned empty transcription")
            return {"text": "", "confidence": 0.0, "language": "en"}

        logger.info(f"[{_stt_type}] Transcribed: '{text[:80]}...'")
        return {
            "text": text,
            "confidence": confidence,
            "language": language,
        }

    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        raise

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        if wav_path and os.path.exists(wav_path):
            os.unlink(wav_path)
