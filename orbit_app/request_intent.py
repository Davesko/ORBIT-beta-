"""Task intent boundaries: source editing is not generative video or image creation."""
import re
from model_router import normalized

def media_intent(prompt):
 p=normalized(prompt)
 if re.search(r'\b(koncepcio\w*kep\w*|konceptkep\w*|concept art|flux|image|imgae|picture|kepet|kepek|foto\w*|illusztracio\w*)\b',p) and re.search(r'general|keszit|create|generate|draw|rajzol|alkoss|make',p):return 'image'
 if re.search(r'\b(shorts?\w*|youtube\w*|tiktok|reels|highlight\w*|clip farm|stream\w*)\b|youtu\.be/',p):return 'shorts'
 if re.search(r'video|klip',p) and re.search(r'general|keszit|generate|create|make|render',p):return 'generate_video'
 return None

def compound_or_scheduled(prompt):
 p=normalized(prompt)
 return bool(re.search(r'\b(holnap\w*|tomorrow|ma ej\w*|ejszaka|kozben|emellett|e mellett|ekozben|kesobb|hetfon|kedden|szerdan|csutortokon|penteken|szombaton|vasarnap|autopilot\w*|email\w*)\b|\b[2-9]\s*(?:db\s*)?(?:youtube\s*)?short',p))

def allow_shortcut(prompt):
 return media_intent(prompt) not in ('image','generate_video') and not compound_or_scheduled(prompt)
