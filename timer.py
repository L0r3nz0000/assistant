from sound import Sound

def set_timer(seconds):
  s = Sound("sounds/timer.mp3")
  s.async_play(delay=seconds)