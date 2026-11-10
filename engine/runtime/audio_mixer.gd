extends Node
class_name AudioMixer
## Three logical channels mirroring the originals: ambient loop, voice (one at a time), SFX (polyphonic).

var ambient: AudioStreamPlayer
var voice: AudioStreamPlayer
var _ambient_rel: String = ""


func _ready() -> void:
	ambient = AudioStreamPlayer.new()
	ambient.name = "Ambient"
	ambient.volume_db = -6.0
	add_child(ambient)
	voice = AudioStreamPlayer.new()
	voice.name = "Voice"
	add_child(voice)


func play_ambient(rel: String) -> void:
	if rel == null or rel == "":
		stop_ambient()
		return
	if rel == _ambient_rel and ambient.playing:
		return
	var stream := Assets.sound(rel)
	if stream == null:
		return
	if stream is AudioStreamWAV:
		stream.loop_mode = AudioStreamWAV.LOOP_FORWARD
		stream.loop_begin = 0
		stream.loop_end = stream.data.size() / (2 if stream.format == AudioStreamWAV.FORMAT_16_BITS else 1) / (2 if stream.stereo else 1)
	_ambient_rel = rel
	ambient.stream = stream
	ambient.play()


func stop_ambient() -> void:
	_ambient_rel = ""
	ambient.stop()


## Plays a voice line, interrupting any current one. Returns when it ends (or immediately if missing).
func play_voice(rel: String) -> void:
	voice.stop()
	var stream := Assets.sound(rel) if rel else null
	if stream == null:
		return
	voice.stream = stream
	voice.play()


func voice_done() -> Signal:
	return voice.finished


func is_voice_playing() -> bool:
	return voice.playing


func stop_voice() -> void:
	voice.stop()


## Fire-and-forget sound effect. Returns the player so callers can await `finished`.
func play_sfx(rel: String) -> AudioStreamPlayer:
	var stream := Assets.sound(rel) if rel else null
	if stream == null:
		return null
	var p := AudioStreamPlayer.new()
	p.stream = stream
	add_child(p)
	p.finished.connect(p.queue_free)
	p.play()
	return p


func stop_all() -> void:
	stop_ambient()
	stop_voice()
	for c in get_children():
		if c != ambient and c != voice and c is AudioStreamPlayer:
			c.queue_free()
