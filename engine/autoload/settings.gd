extends Node
## User preferences (persisted to user://settings.cfg).

signal changed

const PATH := "user://settings.cfg"

## "smooth" = free scale with linear filtering, "integer" = nearest integer multiple, pixel filtering
var scale_mode: String = "smooth"
var fullscreen: bool = false
var games_root_override: String = ""
var master_volume: float = 1.0
## QoL hooks (wired later): show clickable regions, skip intros, etc.
var debug_hotspots: bool = false
var skip_intros: bool = true


func _ready() -> void:
	load_settings()
	apply()


func load_settings() -> void:
	var cf := ConfigFile.new()
	if cf.load(PATH) != OK:
		return
	scale_mode = str(cf.get_value("video", "scale_mode", scale_mode))
	fullscreen = bool(cf.get_value("video", "fullscreen", fullscreen))
	games_root_override = str(cf.get_value("paths", "games_root", games_root_override))
	master_volume = float(cf.get_value("audio", "master", master_volume))
	debug_hotspots = bool(cf.get_value("qol", "debug_hotspots", debug_hotspots))
	skip_intros = bool(cf.get_value("qol", "skip_intros", skip_intros))


func save() -> void:
	var cf := ConfigFile.new()
	cf.set_value("video", "scale_mode", scale_mode)
	cf.set_value("video", "fullscreen", fullscreen)
	cf.set_value("paths", "games_root", games_root_override)
	cf.set_value("audio", "master", master_volume)
	cf.set_value("qol", "debug_hotspots", debug_hotspots)
	cf.set_value("qol", "skip_intros", skip_intros)
	cf.save(PATH)


func apply() -> void:
	var mode := DisplayServer.WINDOW_MODE_FULLSCREEN if fullscreen else DisplayServer.WINDOW_MODE_WINDOWED
	if DisplayServer.window_get_mode() != mode:
		DisplayServer.window_set_mode(mode)
	var bus := AudioServer.get_bus_index("Master")
	AudioServer.set_bus_volume_db(bus, linear_to_db(clampf(master_volume, 0.0001, 1.0)))
	changed.emit()


func set_scale_mode(mode: String) -> void:
	scale_mode = mode
	save()
	apply()


func toggle_fullscreen() -> void:
	fullscreen = not fullscreen
	save()
	apply()
