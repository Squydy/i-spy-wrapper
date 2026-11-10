extends Node
## Runtime asset loader for an installed pack. All paths are pack-relative
## ("images/IC/2_IC_Background.png"); files are loaded lazily and cached per screen.

var pack_path: String = ""
var _textures: Dictionary = {}
var _images: Dictionary = {}
var _sounds: Dictionary = {}
## Pack-relative prefixes that survive clear_screen_cache() (shared UI art).
var persistent_prefixes: PackedStringArray = PackedStringArray(["images/MAIN/", "audio/members/MAIN/"])


func set_pack(path: String) -> void:
	pack_path = path
	clear_all()


func abs_path(rel: String) -> String:
	if rel.is_absolute_path():
		return rel
	return pack_path.path_join(rel)


func exists(rel: String) -> bool:
	return rel != "" and FileAccess.file_exists(abs_path(rel))


func image(rel: String) -> Image:
	if rel == null or rel == "":
		return null
	if _images.has(rel):
		return _images[rel]
	var img := Image.new()
	var err := img.load(abs_path(rel))
	if err != OK:
		push_warning("Assets: failed to load image %s (%d)" % [rel, err])
		_images[rel] = null
		return null
	_images[rel] = img
	return img


func texture(rel: String) -> Texture2D:
	if rel == null or rel == "":
		return null
	if _textures.has(rel):
		return _textures[rel]
	var img := image(rel)
	if img == null:
		_textures[rel] = null
		return null
	var tex := ImageTexture.create_from_image(img)
	_textures[rel] = tex
	return tex


func sound(rel: String) -> AudioStream:
	if rel == null or rel == "":
		return null
	if _sounds.has(rel):
		return _sounds[rel]
	var stream: AudioStream = null
	var p := abs_path(rel)
	if rel.to_lower().ends_with(".wav"):
		stream = WavLoader.load(p)
	elif rel.to_lower().ends_with(".ogg"):
		stream = AudioStreamOggVorbis.load_from_file(p)
	else:
		push_warning("Assets: unsupported audio %s" % rel)
	_sounds[rel] = stream
	return stream


func video(rel: String) -> VideoStream:
	if rel == null or rel == "":
		return null
	var vs := VideoStreamTheora.new()
	vs.file = abs_path(rel)
	return vs


func _is_persistent(rel: String) -> bool:
	for p in persistent_prefixes:
		if rel.begins_with(p):
			return true
	return false


## Drop per-screen media; keep shared UI art.
func clear_screen_cache() -> void:
	for dict in [_textures, _images, _sounds]:
		for k in dict.keys():
			if not _is_persistent(k):
				dict.erase(k)


func clear_all() -> void:
	_textures.clear()
	_images.clear()
	_sounds.clear()
