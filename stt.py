from redirect_output import suppress_stderr, restore_stderr
import speech_recognition as sr
from pydub import AudioSegment
import volume_controller
from sound import Sound
from time import time
import replicate
import threading
import requests
import json

#* vosk-api
import wave
import sys

from vosk import Model, KaldiRecognizer, SetLogLevel
#***

MINIMUM_CONFIDENCE_VOSK = 0.6

def save_audio_to_mp3(audio: sr.AudioData, output_path: str):
  # Ottieni i dati audio grezzi dall'oggetto AudioData
  raw_data = audio.get_raw_data()

  # Crea un oggetto AudioSegment dai dati grezzi
  audio_segment = AudioSegment(
    data=raw_data, 
    sample_width=audio.sample_width, 
    frame_rate=audio.sample_rate, 
    channels=1  # Mono
  )

  # Salva l'audio come file MP3
  audio_segment.export(output_path, format="mp3")

def save_audio_to_wav(audio_data, filename):
  # Converte i dati in formato PCM
  raw_data = audio_data.get_raw_data(convert_rate=44100, convert_width=2)

  # Scrivi i dati in un file WAV
  with wave.open(filename, 'wb') as wf:
    wf.setnchannels(1)      # Mono
    wf.setsampwidth(2)      # 16-bit PCM
    wf.setframerate(44100)  # Frequenza di campionamento 44.1 kHz
    wf.writeframes(raw_data)
    
def upload_audio(audio: sr.AudioData) -> str:
  """
  Carica l'audio su 0x0.st e restituisce l'URL del file caricato.
  
  :param audio: L'oggetto AudioData contenente l'audio
  :return: L'URL del file caricato, o None se non è riuscito a caricare il file.
  """
  file_path = 'sounds/input.mp3'
  
  # Converte il file in mp3 per trasferirlo più velocemente
  save_audio_to_mp3(audio, file_path)
  
  # Apri il file in modalità binaria
  with open(file_path, 'rb') as file:
    # Crea un dizionario con il file da caricare
    files = {'file': file}
    
    # Esegui la richiesta POST
    response = requests.post('http://0x0.st', files=files)
    
    # Controlla la risposta
    if response.status_code == 200:
      return response.text.strip()
    else:
      print(f'Errore nel caricamento del file: {response.status_code}')
      return None

def transcribe_incredibly_fast_whisper(audio: sr.AudioData):
  url = upload_audio(audio)
  
  if url is not None:
    output = replicate.run(
      "vaibhavs10/incredibly-fast-whisper:3ab86df6c8f54c11309d4d1f930ac292bad43ace52d10c80d87eb258b3c9f79c",
      input={
        "task": "transcribe",
        "audio": url,
        "language": "italian", # "language": "None" per riconoscere la lingua in automatico
        "timestamp": "chunk",
        "batch_size": 64,
        "diarise_audio": False
      }
    )
    return output['text']
  else:
    return 

def transcribe_vosk(audio: sr.AudioData):
  save_audio_to_wav(audio, 'sounds/input.wav')
  
  SetLogLevel(0)  # -1 to disable debug messages

  wf = wave.open('sounds/input.wav', "rb")
  if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getcomptype() != "NONE":
    print("Audio file must be WAV format mono PCM.")
    sys.exit(1)

  model = Model(lang="it")

  rec = KaldiRecognizer(model, wf.getframerate())
  rec.SetWords(True)
  rec.SetPartialWords(True)
  
  text = ""

  while True:
    data = wf.readframes(4000)
    if len(data) == 0:
      break
    
    rec.AcceptWaveform(data)

  results = json.loads(rec.FinalResult())
  
  for r in results['result']:
    if r['conf'] >= MINIMUM_CONFIDENCE_VOSK:
      text += r['word'] + ' '
  
  return text.strip()

def listen_prompt(timeout=8, stt_backend='vosk', remove_noise=True):
  # Ottiene la lista delle app che stanno riproducendo audio
  active_sinks = volume_controller.get_playing_audio_apps()

  with open("settings.json", "r") as file:
    settings = json.load(file)

  # Abbassa il volume di tutte le app attive
  for sink_id in active_sinks:
    volume_controller.set_volume(sink_id, settings['volume_decrease'])

  text = ""
  # Inizializza il Recognizer
  r = sr.Recognizer()

  # Riproduce il suono di attivazione
  s = Sound("sounds/active.mp3")
  s.async_play()

  # Ridireziona lo stderr a /dev/null
  old_stderr = suppress_stderr()

  with sr.Microphone() as source:
    r.adjust_for_ambient_noise(source, duration=.5)

    print("Sono in ascolto... parla pure!")
    start = time()
    try:
      audio = r.listen(source, timeout=8, phrase_time_limit=timeout)
      s = Sound('sounds/end.mp3')
      s.async_play()
      print(f"[{time() - start:.2f}s] Audio registrato")

      # Riporta il volume delle app attive al valore iniziale
      for sink_id in active_sinks:
        volume_controller.set_volume(sink_id, 100)

      try:
        if stt_backend.lower() == 'whisper':
          print("Whisper sta elaborando il messaggio...")
          start = time()
          
          text = transcribe_incredibly_fast_whisper(audio)
          print(f"[{time() - start:.2f}s] Messaggio elaborato con whisper")
          
        elif stt_backend.lower() == 'google':
          print("Google sta elaborando il messaggio...")
          start = time()
          
          text = r.recognize_google(audio, language="it-IT")
          print(f"[{time() - start:.2f}s] Messaggio elaborato con google")
        
        elif stt_backend.lower() == 'vosk':
          print("Vosk sta elaborando il messaggio...")
          start = time()
          
          text = transcribe_vosk(audio)
          print(f"[{time() - start:.2f}s] Messaggio elaborato con vosk")
        
      except Exception as e:
        print("Exception:", e)
    except sr.exceptions.WaitTimeoutError:
      print("Exception: WaitTimeoutError")
      print("Scusa, non ho capito.")

  # Ripristina lo stderr
  restore_stderr(old_stderr)
  return text
