"""VoiceGuard compatibility shim pointing to VoiceShield."""

import sys
import voiceshield

sys.modules["voiceguard"] = voiceshield
