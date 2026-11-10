extends Sprite2D
class_name AnimSprite
## Frame-list sprite: each frame is a pack-relative image plus its stage rect
## (Director sprites are positioned by registration point, so rects differ per frame).

signal finished

var frames: Array = []
var rects: Array = []
var fps: float = 10.0
var looping: bool = false
var playing: bool = false
var _t: float = 0.0
var _i: int = 0


func _init() -> void:
	centered = false


func setup(p_frames: Array, p_rects: Array, p_fps: float = 10.0) -> void:
	frames = p_frames
	rects = p_rects
	fps = maxf(p_fps, 1.0)
	_i = 0
	_apply()


## Show a single static image at rect.
func set_static(image: String, rect: Array) -> void:
	setup([image], [rect], fps)


func play(loop: bool = false) -> void:
	if frames.is_empty():
		finished.emit()
		return
	looping = loop
	_i = 0
	_t = 0.0
	playing = true
	_apply()


func stop(frame: int = 0) -> void:
	playing = false
	show_frame(frame)


func show_frame(i: int) -> void:
	if frames.is_empty():
		return
	_i = clampi(i, 0, frames.size() - 1)
	_apply()


func last_frame() -> int:
	return frames.size() - 1


func current_rect() -> Rect2:
	if rects.is_empty():
		return Rect2()
	return _rect(rects[clampi(_i, 0, rects.size() - 1)])


func _process(delta: float) -> void:
	if not playing:
		return
	_t += delta
	var step := 1.0 / fps
	while _t >= step:
		_t -= step
		_i += 1
		if _i >= frames.size():
			if looping:
				_i = 0
			else:
				_i = frames.size() - 1
				playing = false
				_apply()
				finished.emit()
				return
	_apply()


func _apply() -> void:
	if frames.is_empty():
		texture = null
		return
	var idx := clampi(_i, 0, frames.size() - 1)
	texture = Assets.texture(str(frames[idx]))
	var r := _rect(rects[mini(idx, rects.size() - 1)]) if not rects.is_empty() else Rect2()
	position = r.position


static func _rect(a: Variant) -> Rect2:
	if a is Array and a.size() == 4:
		return Rect2(a[0], a[1], a[2] - a[0], a[3] - a[1])
	return Rect2()
