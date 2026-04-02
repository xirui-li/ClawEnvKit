import os
import json
import copy
from fastapi import FastAPI, Request
from pydantic import BaseModel, Field
from typing import Optional, List, Any
import uvicorn

from mock_services._base import add_error_injection, load_fixtures

app = FastAPI(title="Spotify Mock Service")
add_error_injection(app)

_audit_log: List[dict] = []
_state: dict = {"tracks": [], "playlists": [], "playback": {"is_playing": False, "current_track": None, "volume": 50}}
_fixtures: dict = {}

def _log_call(endpoint: str, request_body: Any, response_body: Any):
    _audit_log.append({"endpoint": endpoint, "request": request_body, "response": response_body})

def _load_fixtures():
    global _state, _fixtures
    fixtures_path = os.environ.get("SPOTIFY_FIXTURES", "")
    if fixtures_path and os.path.exists(fixtures_path):
        with open(fixtures_path, "r") as f:
            data = json.load(f)
        _fixtures = copy.deepcopy(data)
    else:
        _fixtures = {
            "tracks": [
                {"id": "t1", "title": "Bohemian Rhapsody", "artist": "Queen", "album": "A Night at the Opera", "duration_ms": 355000, "genre": "rock"},
                {"id": "t2", "title": "Blinding Lights", "artist": "The Weeknd", "album": "After Hours", "duration_ms": 200040, "genre": "pop"},
                {"id": "t3", "title": "Shape of You", "artist": "Ed Sheeran", "album": "Divide", "duration_ms": 233712, "genre": "pop"},
                {"id": "t4", "title": "Hotel California", "artist": "Eagles", "album": "Hotel California", "duration_ms": 391000, "genre": "rock"},
                {"id": "t5", "title": "Levitating", "artist": "Dua Lipa", "album": "Future Nostalgia", "duration_ms": 203064, "genre": "pop"}
            ],
            "playlists": [
                {"id": "p1", "name": "My Favorites", "description": "A collection of my favorite songs", "track_ids": ["t1", "t2"], "owner": "user1"},
                {"id": "p2", "name": "Chill Vibes", "description": "Relaxing music for any time", "track_ids": ["t3", "t5"], "owner": "user1"}
            ],
            "playback": {"is_playing": False, "current_track": None, "volume": 50}
        }
    _state = copy.deepcopy(_fixtures)

_load_fixtures()

# --- Pydantic Models ---

class SearchTracksRequest(BaseModel):
    query: Optional[str] = None
    genre: Optional[str] = None
    artist: Optional[str] = None
    limit: Optional[int] = 20

class GetTrackRequest(BaseModel):
    track_id: str

class PlaybackControlRequest(BaseModel):
    action: str  # play, pause, next, previous
    track_id: Optional[str] = None
    volume: Optional[int] = None

class ListPlaylistsRequest(BaseModel):
    owner: Optional[str] = None

class CreatePlaylistRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    track_ids: Optional[List[str]] = Field(default_factory=list)
    owner: Optional[str] = "user1"

class UpdatePlaylistRequest(BaseModel):
    playlist_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    track_ids: Optional[List[str]] = None

class DeletePlaylistRequest(BaseModel):
    playlist_id: str

class GetCurrentTrackRequest(BaseModel):
    pass

# --- Endpoints ---

@app.post("/spotify/search_tracks")
def search_tracks(req: SearchTracksRequest):
    results = list(_state["tracks"])
    if req.query:
        q = req.query.lower()
        results = [t for t in results if q in t["title"].lower() or q in t["artist"].lower() or q in t["album"].lower()]
    if req.genre:
        results = [t for t in results if t.get("genre", "").lower() == req.genre.lower()]
    if req.artist:
        results = [t for t in results if req.artist.lower() in t["artist"].lower()]
    results = results[:req.limit]
    response = {"tracks": results, "total": len(results)}
    _log_call("/spotify/search_tracks", req.dict(), response)
    return response

@app.post("/spotify/get_track")
def get_track(req: GetTrackRequest):
    track = next((t for t in _state["tracks"] if t["id"] == req.track_id), None)
    if track is None:
        response = {"error": f"Track '{req.track_id}' not found"}
        _log_call("/spotify/get_track", req.dict(), response)
        return response
    response = {"track": track}
    _log_call("/spotify/get_track", req.dict(), response)
    return response

@app.post("/spotify/playback_control")
def playback_control(req: PlaybackControlRequest):
    playback = _state["playback"]
    action = req.action.lower()
    if action == "play":
        if req.track_id:
            track = next((t for t in _state["tracks"] if t["id"] == req.track_id), None)
            if track is None:
                response = {"error": f"Track '{req.track_id}' not found"}
                _log_call("/spotify/playback_control", req.dict(), response)
                return response
            playback["current_track"] = track
        if playback["current_track"] is None and _state["tracks"]:
            playback["current_track"] = _state["tracks"][0]
        playback["is_playing"] = True
    elif action == "pause":
        playback["is_playing"] = False
    elif action == "next":
        tracks = _state["tracks"]
        if tracks and playback["current_track"]:
            idx = next((i for i, t in enumerate(tracks) if t["id"] == playback["current_track"]["id"]), -1)
            next_idx = (idx + 1) % len(tracks)
            playback["current_track"] = tracks[next_idx]
            playback["is_playing"] = True
        elif tracks:
            playback["current_track"] = tracks[0]
            playback["is_playing"] = True
    elif action == "previous":
        tracks = _state["tracks"]
        if tracks and playback["current_track"]:
            idx = next((i for i, t in enumerate(tracks) if t["id"] == playback["current_track"]["id"]), 0)
            prev_idx = (idx - 1) % len(tracks)
            playback["current_track"] = tracks[prev_idx]
            playback["is_playing"] = True
    elif action == "set_volume":
        if req.volume is not None:
            playback["volume"] = max(0, min(100, req.volume))
    else:
        response = {"error": f"Unknown action '{req.action}'. Use play, pause, next, previous, set_volume"}
        _log_call("/spotify/playback_control", req.dict(), response)
        return response
    response = {"playback": playback}
    _log_call("/spotify/playback_control", req.dict(), response)
    return response

@app.post("/spotify/get_current_track")
def get_current_track(req: GetCurrentTrackRequest):
    response = {"playback": _state["playback"]}
    _log_call("/spotify/get_current_track", req.dict(), response)
    return response

@app.post("/spotify/list_playlists")
def list_playlists(req: ListPlaylistsRequest):
    playlists = list(_state["playlists"])
    if req.owner:
        playlists = [p for p in playlists if p.get("owner", "") == req.owner]
    enriched = []
    for pl in playlists:
        track_list = [t for t in _state["tracks"] if t["id"] in pl.get("track_ids", [])]
        enriched.append({**pl, "tracks": track_list, "track_count": len(track_list)})
    response = {"playlists": enriched, "total": len(enriched)}
    _log_call("/spotify/list_playlists", req.dict(), response)
    return response

@app.post("/spotify/create_playlist")
def create_playlist(req: CreatePlaylistRequest):
    import uuid
    new_id = "p" + str(uuid.uuid4())[:8]
    valid_track_ids = [tid for tid in (req.track_ids or []) if any(t["id"] == tid for t in _state["tracks"])]
    playlist = {
        "id": new_id,
        "name": req.name,
        "description": req.description or "",
        "track_ids": valid_track_ids,
        "owner": req.owner or "user1"
    }
    _state["playlists"].append(playlist)
    response = {"playlist": playlist, "created": True}
    _log_call("/spotify/create_playlist", req.dict(), response)
    return response

@app.post("/spotify/update_playlist")
def update_playlist(req: UpdatePlaylistRequest):
    playlist = next((p for p in _state["playlists"] if p["id"] == req.playlist_id), None)
    if playlist is None:
        response = {"error": f"Playlist '{req.playlist_id}' not found"}
        _log_call("/spotify/update_playlist", req.dict(), response)
        return response
    if req.name is not None:
        playlist["name"] = req.name
    if req.description is not None:
        playlist["description"] = req.description
    if req.track_ids is not None:
        valid_track_ids = [tid for tid in req.track_ids if any(t["id"] == tid for t in _state["tracks"])]
        playlist["track_ids"] = valid_track_ids
    response = {"playlist": playlist, "updated": True}
    _log_call("/spotify/update_playlist", req.dict(), response)
    return response

@app.post("/spotify/delete_playlist")
def delete_playlist(req: DeletePlaylistRequest):
    playlist = next((p for p in _state["playlists"] if p["id"] == req.playlist_id), None)
    if playlist is None:
        response = {"error": f"Playlist '{req.playlist_id}' not found"}
        _log_call("/spotify/delete_playlist", req.dict(), response)
        return response
    _state["playlists"] = [p for p in _state["playlists"] if p["id"] != req.playlist_id]
    response = {"deleted": True, "playlist_id": req.playlist_id}
    _log_call("/spotify/delete_playlist", req.dict(), response)
    return response

@app.get("/spotify/audit")
def audit():
    return {"calls": _audit_log}

@app.post("/spotify/reset")
def reset():
    global _state
    _audit_log.clear()
    _load_fixtures()
    return {"reset": True}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 9120))
    uvicorn.run(app, host="0.0.0.0", port=port)
