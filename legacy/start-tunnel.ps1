# Baut den verschluesselten SSH-Rueckwaertstunnel PC -> Reachy auf.
# Danach erreicht die Conversation-App auf dem Roboter
#   127.0.0.1:8765 -> Sprach-Backend (speech-to-speech) auf dem PC
#   127.0.0.1:8787 -> claude-bridge auf dem PC
# ohne dass einer der beiden Dienste im WLAN offen ist.
param(
    [string]$Robot = "reachy-mini.local",
    [string]$User = "pollen"
)
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 `
    -R 127.0.0.1:8765:127.0.0.1:8765 `
    -R 127.0.0.1:8787:127.0.0.1:8787 `
    "$User@$Robot"
