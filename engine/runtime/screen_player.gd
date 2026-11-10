extends Node2D
class_name ScreenPlayer
## Plays the normalized screen JSON produced by the extractor (scenes/<ID>.json).
## Two screen kinds are supported by the shared loop:
##   "nav"    - a background with animated navigation buttons leading to other screens
##   "riddle" - an I SPY picture: riddle strip, clickable objects, end animation, map clue
## Everything is expressed in stage coordinates; the parent Stage node handles scaling.

signal screen_changed(id: String)
signal request_exit
signal toast(text: String)

var pack: Dictionary = {}       # manifest
var index: Dictionary = {}      # scenes/index.json
var screen: Dictionary = {}     # current screen json
var variant: Dictionary = {}    # current riddle variant (hunt)
var hunt: String = "A"
var history: Array[String] = []

var mixer: AudioMixer
var layer_bg: Node2D
var layer_objects: Node2D
var layer_strip: Node2D
var layer_ui: Node2D
var layer_debug: Node2D

var hotspots: Array[Hotspot] = []
var busy: bool = false
var _hover: Hotspot = null
var _pressed: Hotspot = null

# riddle state
var _objects: Dictionary = {}    # id -> {hs, anim, data, found}
var _words: Dictionary = {}      # id -> {sprite, data}
var _multi_parts: Dictionary = {} # object id -> found parts count


func _ready() -> void:
	mixer = AudioMixer.new()
	add_child(mixer)
	for n in ["bg", "objects", "strip", "ui", "debug"]:
		var l := Node2D.new()
		l.name = n
		add_child(l)
	layer_bg = get_node("bg")
	layer_objects = get_node("objects")
	layer_strip = get_node("strip")
	layer_ui = get_node("ui")
	layer_debug = get_node("debug")
	layer_debug.draw.connect(_draw_debug)
	Settings.changed.connect(func(): layer_debug.queue_redraw())


# ----------------------------------------------------------------------------- loading
func load_pack(manifest: Dictionary) -> bool:
	pack = manifest
	Assets.set_pack(manifest["path"])
	var idx = Library.load_json(Assets.abs_path("scenes/index.json"))
	if not (idx is Dictionary):
		push_error("pack has no scenes/index.json")
		return false
	index = idx
	Saves.open(str(manifest.get("id", "")))
	hunt = Saves.get_hunt()
	var start := Saves.get_screen()
	if start == "" or not _screen_exists(start):
		start = str(index.get("entry", ""))
	return go_to(start, false)


func stage_size() -> Vector2:
	var st: Dictionary = index.get("stage", pack.get("stage", {}))
	return Vector2(float(st.get("width", 640)), float(st.get("height", 480)))


func _screen_exists(id: String) -> bool:
	return FileAccess.file_exists(Assets.abs_path("scenes/%s.json" % id))


func go_to(id: String, push_history: bool = true) -> bool:
	if id == "" or not _screen_exists(id):
		toast.emit("Screen %s is not available" % id)
		return false
	var data = Library.load_json(Assets.abs_path("scenes/%s.json" % id))
	if not (data is Dictionary):
		return false
	if push_history and screen.has("id"):
		history.append(str(screen["id"]))
	_clear()
	Assets.clear_screen_cache()
	screen = data
	Saves.set_screen(id)
	match str(screen.get("kind", "")):
		"nav":
			_build_nav()
		"riddle":
			_build_riddle()
		_:
			_build_generic()
	busy = false
	layer_debug.queue_redraw()
	screen_changed.emit(id)
	return true


func go_back() -> void:
	var back := str(screen.get("back", "")) if screen.get("back") != null else ""
	if back == "" and not history.is_empty():
		back = history.pop_back()
	if back != "":
		go_to(back)


func set_hunt(h: String) -> void:
	if h == hunt:
		return
	hunt = h
	Saves.set_hunt(h)
	if screen.get("kind", "") == "riddle":
		go_to(str(screen["id"]), false)


func _clear() -> void:
	hotspots.clear()
	_hover = null
	_pressed = null
	_objects.clear()
	_words.clear()
	_multi_parts.clear()
	mixer.stop_voice()
	for layer in [layer_bg, layer_objects, layer_strip, layer_ui]:
		for c in layer.get_children():
			c.queue_free()


# ----------------------------------------------------------------------------- helpers
func _sprite(parent: Node2D, image: String, rect: Variant) -> Sprite2D:
	var s := Sprite2D.new()
	s.centered = false
	s.texture = Assets.texture(image)
	var r := Hotspot.rect_from(rect)
	s.position = r.position
	parent.add_child(s)
	return s


func _anim(parent: Node2D, frames: Array, rects: Array, fps: float) -> AnimSprite:
	var a := AnimSprite.new()
	parent.add_child(a)
	a.setup(frames, rects, fps)
	return a


func _add_hotspot(hs: Hotspot) -> Hotspot:
	hotspots.append(hs)
	return hs


func _rect_union(rects: Array, base: Rect2) -> Rect2:
	var r := base
	for a in rects:
		r = r.merge(Hotspot.rect_from(a))
	return r


# ----------------------------------------------------------------------------- generic (fallback) screens
func _build_generic() -> void:
	if screen.get("background"):
		_sprite(layer_bg, screen["background"], [0, 0, 0, 0])
	mixer.play_ambient(str(screen.get("ambient", "")) if screen.get("ambient") else "")


# ----------------------------------------------------------------------------- nav screens
func _build_nav() -> void:
	_sprite(layer_bg, screen["background"], [0, 0, 0, 0])
	mixer.play_ambient(str(screen.get("ambient", "")) if screen.get("ambient") else "")

	for nav in screen.get("navs", []):
		_build_nav_button(nav)
	for side in screen.get("sideNavs", []):
		var hs := Hotspot.new("side:" + str(side.get("id", "")), Hotspot.rect_from(side.get("rect")))
		hs.on_enter = func(): mixer.play_sfx(str(side.get("rollSound", "")) if side.get("rollSound") else "")
		hs.on_click = func():
			if side.get("downSound"):
				mixer.play_sfx(str(side["downSound"]))
			go_to(str(side.get("dest", "")))
		_add_hotspot(hs)
	for btn in screen.get("buttons", []):
		_build_button(btn)


func _build_nav_button(nav: Dictionary) -> void:
	var frames: Array = nav.get("frames", [])
	var rects: Array = nav.get("frameRects", [])
	if frames.is_empty():
		frames = [nav["image"]]
		rects = [nav["rect"]]
	var anim := _anim(layer_objects, frames, rects, float(nav.get("fps", 8)))
	var hit_rect := _rect_union(rects, Hotspot.rect_from(nav["rect"]))
	hit_rect = _rect_union(nav.get("endFrameRects", []), hit_rect)
	var hs := Hotspot.new("nav:" + str(nav.get("id", "")), hit_rect, str(nav["image"]))
	# the alpha test is against the neutral image, which sits at nav.rect
	hs.rect = Hotspot.rect_from(nav["rect"])
	hs.tag = hit_rect
	hs.on_enter = func():
		anim.play(true)
		if nav.get("rollSound"):
			mixer.play_sfx(str(nav["rollSound"]))
	hs.on_exit = func(): anim.stop(0)
	hs.on_click = func(): _nav_click(nav, anim)
	_add_hotspot(hs)


func _nav_click(nav: Dictionary, anim: AnimSprite) -> void:
	if busy:
		return
	busy = true
	if nav.get("downSound"):
		mixer.play_sfx(str(nav["downSound"]))
	var end_frames: Array = nav.get("endFrames", [])
	if not end_frames.is_empty():
		anim.setup(end_frames, nav.get("endFrameRects", []), float(nav.get("fps", 8)))
		anim.play(false)
		await anim.finished
	else:
		anim.stop(0)
		await get_tree().create_timer(0.15).timeout
	busy = false
	go_to(str(nav.get("dest", "")))


# ----------------------------------------------------------------------------- buttons
func _build_button(btn: Dictionary, parent: Node2D = null) -> Hotspot:
	var spr := _sprite(parent if parent else layer_ui, btn["image"], btn["rect"])
	var hs := Hotspot.new("btn:" + str(btn.get("id", "")), Hotspot.rect_from(btn["rect"]), str(btn["image"]))
	hs.on_enter = func():
		if btn.get("rollImage"):
			spr.texture = Assets.texture(str(btn["rollImage"]))
		if btn.get("rollSound"):
			mixer.play_sfx(str(btn["rollSound"]))
	hs.on_exit = func(): spr.texture = Assets.texture(str(btn["image"]))
	hs.on_click = func():
		if btn.get("downImage"):
			spr.texture = Assets.texture(str(btn["downImage"]))
		if btn.get("downSound"):
			mixer.play_sfx(str(btn["downSound"]))
		await get_tree().create_timer(0.12).timeout
		if is_instance_valid(spr):
			spr.texture = Assets.texture(str(btn["image"]))
		if btn.get("upSound"):
			mixer.play_sfx(str(btn["upSound"]))
		_button_action(str(btn.get("action", "")), btn)
	_add_hotspot(hs)
	return hs


func _button_action(action: String, btn: Dictionary) -> void:
	match action:
		"back":
			go_back()
		"map":
			toast.emit("Map: %d of %d riddles solved on hunt %s" % [Saves.solved_count(hunt), _riddle_count(), hunt])
		"help":
			toast.emit("Click the things named on the riddle strip at the bottom of the picture.")
		"newgame":
			Saves.reset()
			go_to(str(index.get("entry", "")), false)
		"quit":
			request_exit.emit()
		"readriddle":
			var strip: Dictionary = variant.get("strip", {})
			if strip.get("riddleAudio"):
				mixer.play_voice(str(strip["riddleAudio"]))
		_:
			toast.emit("Button '%s' is not implemented yet" % action)


func _riddle_count() -> int:
	var n := 0
	for s in index.get("screens", []):
		if s.get("kind", "") == "riddle":
			n += 1
	return n


# ----------------------------------------------------------------------------- riddle screens
func _build_riddle() -> void:
	var variants: Dictionary = screen.get("variants", {})
	if variants.is_empty():
		_build_generic()
		return
	variant = variants.get(hunt, variants.values()[0])
	var sid := str(screen["id"])
	_sprite(layer_bg, variant["background"], [0, 0, 0, 0])
	mixer.play_ambient(str(variant.get("ambient", "")) if variant.get("ambient") else "")

	# objects (draw order = list order; hit test is reversed so top-most wins)
	for obj in variant.get("objects", []):
		if obj.get("multi", false):
			_build_multi_object(obj, sid)
		else:
			_build_object(obj, sid, obj["id"])

	var solved := Saves.is_solved(sid, hunt)
	if solved:
		_show_map_strip(false)
	else:
		_build_strip(sid)
	for btn in variant.get("buttons", []):
		_build_button(btn)

	if not solved and _all_words_found(sid):
		# everything was found but the solve sequence was interrupted
		_solve_sequence.call_deferred()


func _build_object(obj: Dictionary, sid: String, word_id: String, parent_multi: String = "") -> void:
	var found := Saves.is_found(sid, hunt, str(obj["id"]))
	var frames: Array = obj.get("frames", [])
	var rects: Array = obj.get("frameRects", [])
	if frames.is_empty():
		frames = [obj["image"]]
		rects = [obj["rect"]]
	var anim := _anim(layer_objects, frames, rects, float(obj.get("fps", 10)))
	if found and obj.get("foundImage"):
		anim.set_static(str(obj["foundImage"]), obj["foundRect"])

	var hs: Hotspot
	var hot: Variant = obj.get("foundHotspot") if (found and obj.get("foundHotspot")) else obj.get("hotspot")
	if hot:
		hs = Hotspot.new("obj:" + str(obj["id"]), Hotspot.rect_from(hot))
	else:
		var img := str(obj["foundImage"]) if (found and obj.get("foundImage")) else str(obj["image"])
		var rect: Variant = obj["foundRect"] if (found and obj.get("foundImage")) else obj["rect"]
		hs = Hotspot.new("obj:" + str(obj["id"]), Hotspot.rect_from(rect), img)
	hs.on_click = func(): _object_click(obj, sid, word_id, parent_multi)
	_add_hotspot(hs)
	_objects[str(obj["id"])] = {"hs": hs, "anim": anim, "data": obj, "found": found}


func _build_multi_object(obj: Dictionary, sid: String) -> void:
	var oid := str(obj["id"])
	var n := 0
	for part in obj.get("parts", []):
		_build_object(part, sid, oid, oid)
		if Saves.is_found(sid, hunt, str(part["id"])):
			n += 1
	_multi_parts[oid] = n
	_objects[oid] = {"data": obj, "found": Saves.is_found(sid, hunt, oid), "multi": true}


func _object_click(obj: Dictionary, sid: String, word_id: String, parent_multi: String) -> void:
	if busy:
		return
	busy = true
	var entry: Dictionary = _objects[str(obj["id"])]
	var anim: AnimSprite = entry["anim"]
	var was_found: bool = entry["found"]
	var sound := str(obj.get("sound", "")) if obj.get("sound") else ""

	if parent_multi != "":
		var multi: Dictionary = _objects[parent_multi]["data"]
		var sounds: Array = multi.get("clickSounds", [])
		if not was_found:
			var k: int = _multi_parts.get(parent_multi, 0)
			var parts: Array = multi.get("parts", [])
			var all_done: bool = k + 1 >= parts.size()
			var s: Variant = null
			if all_done and multi.get("allFoundSound"):
				s = multi["allFoundSound"]
			elif not sounds.is_empty():
				s = sounds[mini(k, sounds.size() - 1)]
			if s:
				sound = str(s)

	if sound != "":
		mixer.play_voice(sound)
	anim.setup(obj.get("frames", [obj["image"]]), obj.get("frameRects", [obj["rect"]]), float(obj.get("fps", 10)))
	anim.play(false)
	await anim.finished
	if not is_instance_valid(anim):
		return
	if not obj.get("stateChange", false) and not obj.get("foundImage"):
		anim.show_frame(0)
	elif obj.get("foundImage"):
		anim.set_static(str(obj["foundImage"]), obj["foundRect"])
	if obj.get("foundHotspot"):
		entry["hs"].rect = Hotspot.rect_from(obj["foundHotspot"])
		entry["hs"].image = ""

	if not was_found:
		entry["found"] = true
		Saves.mark_found(sid, hunt, str(obj["id"]))
		var word_done := true
		if parent_multi != "":
			_multi_parts[parent_multi] = _multi_parts.get(parent_multi, 0) + 1
			word_done = _multi_parts[parent_multi] >= _objects[parent_multi]["data"].get("parts", []).size()
			if word_done:
				_objects[parent_multi]["found"] = true
				Saves.mark_found(sid, hunt, parent_multi)
		if word_done:
			_mark_word_found(word_id)
	if mixer.is_voice_playing():
		await mixer.voice_done()
	busy = false
	if not Saves.is_solved(sid, hunt) and _all_words_found(sid):
		_solve_sequence()


# ---- riddle strip
func _build_strip(sid: String) -> void:
	var strip: Dictionary = variant.get("strip", {})
	if strip.get("paperImage"):
		_sprite(layer_strip, strip["paperImage"], strip["paperRect"])
	if strip.get("riddleImage"):
		_sprite(layer_strip, strip["riddleImage"], strip["riddleRect"])
	for w in variant.get("words", []):
		var wid := str(w["id"])
		var spr: Sprite2D = null
		if w.get("foundImage"):
			spr = _sprite(layer_strip, w["foundImage"], w["foundRect"])
			spr.visible = Saves.is_found(sid, hunt, wid)
		_words[wid] = {"sprite": spr, "data": w}
		if w.get("rect"):
			var hs := Hotspot.new("word:" + wid, Hotspot.rect_from(w["rect"]))
			hs.on_click = func():
				if w.get("sound"):
					mixer.play_voice(str(w["sound"]))
			_add_hotspot(hs)
	for x in variant.get("extraWords", []):
		if x.get("rect"):
			var hs := Hotspot.new("word:extra", Hotspot.rect_from(x["rect"]))
			hs.on_click = func():
				if x.get("sound"):
					mixer.play_voice(str(x["sound"]))
			_add_hotspot(hs)
	if strip.get("ear"):
		_build_button(strip["ear"], layer_strip)


func _mark_word_found(word_id: String) -> void:
	if _words.has(word_id) and _words[word_id]["sprite"]:
		_words[word_id]["sprite"].visible = true


func _all_words_found(sid: String) -> bool:
	var words: Array = variant.get("words", [])
	if words.is_empty():
		return false
	for w in words:
		if not Saves.is_found(sid, hunt, str(w["id"])):
			return false
	return true


# ---- solve: congratulation -> end animation -> map piece -> map clue strip
func _solve_sequence() -> void:
	var sid := str(screen["id"])
	busy = true
	if variant.get("congratsAudio"):
		mixer.play_voice(str(variant["congratsAudio"]))
		await mixer.voice_done()
	var end: Variant = variant.get("endAnim")
	if end is Dictionary and not end.get("frames", []).is_empty():
		var anim := _anim(layer_objects, end["frames"], end["frameRects"], float(end.get("fps", 10)))
		if end.get("sound"):
			mixer.play_sfx(str(end["sound"]))
		anim.play(false)
		await anim.finished
		Saves.mark_solved(sid, hunt)
		var click_rect := Hotspot.rect_from(end.get("clickRect")) if end.get("clickRect") else anim.current_rect()
		var hs := Hotspot.new("endanim", click_rect)
		hs.on_click = func():
			hs.enabled = false
			if variant.get("mapGoneAudio"):
				mixer.play_voice(str(variant["mapGoneAudio"]))
			anim.queue_free()
			_show_map_strip(true)
		_add_hotspot(hs)
		busy = false
		toast.emit("You found everything! Click the map piece.")
	else:
		Saves.mark_solved(sid, hunt)
		_show_map_strip(true)
		busy = false


func _show_map_strip(play_audio: bool) -> void:
	for c in layer_strip.get_children():
		c.queue_free()
	hotspots = hotspots.filter(func(h): return not (h.id.begins_with("word:") or h.id == "btn:gl_ear"))
	var mp: Variant = variant.get("mapStrip")
	if mp is Dictionary:
		if mp.get("paperImage"):
			_sprite(layer_strip, mp["paperImage"], mp["paperRect"])
		if mp.get("image"):
			_sprite(layer_strip, mp["image"], mp["rect"])
			var hs := Hotspot.new("mapclue", Hotspot.rect_from(mp["rect"]))
			hs.on_click = func():
				if mp.get("audio"):
					mixer.play_voice(str(mp["audio"]))
			_add_hotspot(hs)
		if play_audio and mp.get("audio"):
			mixer.play_voice(str(mp["audio"]))
	layer_debug.queue_redraw()


# ----------------------------------------------------------------------------- input
func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion:
		_update_hover(get_local_mouse_position())
	elif event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		var p := get_local_mouse_position()
		if event.pressed:
			_pressed = _hit(p)
		else:
			var hs := _hit(p)
			if hs != null and hs == _pressed and not busy and hs.on_click.is_valid():
				hs.on_click.call()
			_pressed = null
		_update_hover(p)


func _hit(p: Vector2) -> Hotspot:
	for i in range(hotspots.size() - 1, -1, -1):
		var hs := hotspots[i]
		if hs.hit(p):
			return hs
	return null


func _update_hover(p: Vector2) -> void:
	var hs := _hit(p) if not busy else null
	if hs == _hover:
		return
	if _hover != null:
		_hover.hovered = false
		if _hover.on_exit.is_valid():
			_hover.on_exit.call()
	_hover = hs
	if _hover != null:
		_hover.hovered = true
		if _hover.on_enter.is_valid():
			_hover.on_enter.call()
	Input.set_default_cursor_shape(Input.CURSOR_POINTING_HAND if _hover != null else Input.CURSOR_ARROW)


func _process(_delta: float) -> void:
	if busy and _hover != null:
		_update_hover(Vector2(-1, -1))


# ----------------------------------------------------------------------------- debug overlay (QoL hook)
func _draw_debug() -> void:
	if not Settings.debug_hotspots:
		return
	for hs in hotspots:
		if not hs.enabled:
			continue
		var col := Color(1, 0.3, 0.3, 0.8) if hs.id.begins_with("obj:") else Color(0.3, 0.8, 1, 0.8)
		layer_debug.draw_rect(hs.rect, col, false, 1.0)
