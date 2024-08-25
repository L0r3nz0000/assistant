from redirect_output import suppress_stderr, restore_stderr
from raspberry_pi import is_raspberry_pi
from updates import fetch_updates
import pvporcupine
import threading
import pyaudio
import struct
import signal
import os

access_key = "KLlwjiQgPwLdfVFeikjfBtM/+8GnlLdCvlQaLAtUwUVDDr4jPNEgdw=="

linux_keyword_path = "wake_word_models/jarvis_it_linux_v3_0_0.ppn"
raspberry_keyword_path = "wake_word_models/Jarvis_it_raspberry-pi_v3_0_0.ppn"

# Carica il modello adatto per la piattaforma
keyword_path = linux_keyword_path if not is_raspberry_pi() else raspberry_keyword_path
model_path = "wake_word_models/porcupine_params_it.pv"

def get_next_audio_frame(): pass

# Aspetta la parola di attivazione
def blocking_wake_word(conversation_open, response_completed, update_available):
  handle = pvporcupine.create(
    access_key=access_key,
    keyword_paths=[keyword_path],
    model_path=model_path
  )

  old_stderr = suppress_stderr()

  pa = pyaudio.PyAudio()

  audio_stream = pa.open(
    rate=handle.sample_rate,
    channels=1,
    format=pyaudio.paInt16,
    input=True,
    frames_per_buffer=handle.frame_length)
  
  print("Aspetto la parola di attivazione...")

  try:
    while True:
      if update_available.is_set():
        return False
      if response_completed.is_set() and conversation_open.is_set():
        return True
      
      pcm = audio_stream.read(handle.frame_length)
      pcm = struct.unpack_from("h" * handle.frame_length, pcm)
      keyword_index = handle.process(pcm)
      if keyword_index >= 0:
        print("Attivo")
        return True
  finally:
    audio_stream.close()        # Chiude lo stream audio
    pa.terminate()              # Termina PyAudio
    handle.delete()             # Elimina l'handle di Porcupine
    restore_stderr(old_stderr)  # Ripristina lo stderr