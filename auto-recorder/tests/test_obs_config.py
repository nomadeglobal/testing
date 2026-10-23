import json
import os
import tomllib

ROOT = os.path.join(os.path.dirname(__file__), "..")


def test_scene_collection_matches_config():
    with open(os.path.join(ROOT, "config.example.toml"), "rb") as f:
        cfg = tomllib.load(f)
    with open(os.path.join(ROOT, "obs-config", "Webinaire.scene-collection.json"), encoding="utf-8") as f:
        col = json.load(f)
    names = {s["name"]: s for s in col["sources"]}
    assert cfg["obs"]["scene"] == col["current_program_scene"] and names[cfg["obs"]["scene"]]["id"] == "scene"
    assert names[cfg["obs"]["audio_source"]]["id"] == "wasapi_process_output_capture"
    in_scene = {i["name"] for i in names[cfg["obs"]["scene"]]["settings"]["items"]}
    assert in_scene <= set(names)
    assert cfg["obs"]["audio_source"] in in_scene
