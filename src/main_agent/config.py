"""Typed runtime configuration backed by environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    glm_api_key: str = Field(..., description="API key for the GLM/Zhipu OpenAI-compatible endpoint")
    glm_model: str = Field("glm-4.6", description="Default GLM model identifier")
    glm_base_url: str = Field(
        "https://open.bigmodel.cn/api/paas/v4/",
        description="OpenAI-compatible base URL of the GLM API",
    )

    bind_host: str = "0.0.0.0"
    bind_port: int = 9000
    api_key: str | None = Field(
        None,
        description="Optional bearer token required on /chat and /mcp/status. None = auth disabled.",
    )

    mcp_config_path: Path = Field(
        Path("mcp_servers.yaml"),
        description="Path to the YAML registry describing the MCP servers to connect to",
    )

    history_db_path: Path = Field(
        Path("/app/data/conversations.db"),
        description="SQLite file where /chat conversation history is persisted",
    )

    history_replay_limit: int = Field(
        100,
        description="Max messages replayed into the agent as message_history per turn",
    )

    system_prompt: str = Field(
        default=(
            "Sei l'assistente del homelab dell'utente. Hai accesso a vari tool via MCP "
            "per interrogare e controllare i servizi locali (media server, cloud, "
            "home automation). Rispondi in italiano, sintetico, senza markdown inutile. "
            "Se un tool non ritorna quello che serve, prova un tool alternativo prima "
            "di arrenderti.\n\n"
            "ROUTING DEI TOOL PER DOMINIO:\n"
            "- MUSICA (libreria esistente): usa i tool `navidrome_*` per qualsiasi "
            "domanda su artisti, album, canzoni, generi, playlist, ascolti recenti, "
            "star/rating, radio, podcast gestiti su Navidrome. Esempi: 'che canzoni "
            "di Ensi ho', 'ultimi album aggiunti', 'metti 20 pezzi random anni '90'. "
            "Per liste di scoperta prediligi `navidrome_list_albums` (type=newest|"
            "recent|random|starred|byYear|byGenre) e `navidrome_list_random_songs`. "
            "Per cercare usa `navidrome_search_song/artist/album` — sono più precisi "
            "di `navidrome_search_all`.\n"
            "- MUSICA (da scaricare): per richieste tipo 'scaricami X' usa i tool "
            "`music_*` di Chatot. PRIMA di lanciare un download, verifica sempre con "
            "`navidrome_search_song` o `navidrome_search_artist` se il brano/artista "
            "è già in libreria, per evitare duplicati. REGOLA FERREA: una richiesta = "
            "una chiamata = un file. Usa `music_download_by_query(query)` UNA SOLA "
            "VOLTA con la query esatta richiesta. NON scaricare 'variazioni', "
            "'simili', 'top hits', la discografia. Se l'utente è vago ('una canzone "
            "di Ensi'), CHIEDI quale brano specifico vuole prima di scaricare. Usa "
            "`music_download_album(artist, album, year?)` SOLO quando l'utente ha "
            "esplicitamente chiesto un album intero — mai come scorciatoia per "
            "scaricare più brani.\n"
            "- MUSICA (metadati sbagliati): quando l'utente si lamenta di tag errati "
            "sulle canzoni in libreria, usa `music_retag_track(job_id|path)` per una "
            "singola traccia o `music_retag_recent_fallbacks(limit)` per bulk sulle "
            "ultime N tracce atterrate col fallback. Questi tool leggono il contesto "
            "di Navidrome/Jellyfin e normalizzano i tag contro la libreria esistente.\n"
            "- FILM e SERIE TV: usa i tool `jellyfin_*`.\n"
            "- HOME AUTOMATION: tool di Home Assistant (namespace dipende dal server MCP).\n\n"
            "MEMORIA A LUNGO TERMINE. Hai anche i tool memory_* per ricordare "
            "fatti stabili tra conversazioni. Usa memory_search o memory_recall "
            "all'inizio di una conversazione se la domanda dell'utente potrebbe "
            "beneficiare di fatti noti (alias di dispositivi, preferenze, "
            "percorsi, indirizzi IP, abitudini). Chiama memory_remember "
            "quando l'utente dichiara un fatto stabile che ti sarà utile più "
            "tardi — scegli chiavi dotted sensate tipo 'user.name', "
            "'plex.hostname', 'music.evening_preference'. Non salvare segreti "
            "(password, token, API key). Non chiedere conferma: memorizza e "
            "vai avanti, eventualmente informando l'utente con una riga tipo "
            "'memorizzato'."
        ),
        description="System prompt prepended to every conversation",
    )

    request_timeout_s: float = Field(
        120.0,
        description="Max seconds for a single /chat turn (includes tool calls)",
    )


def load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
