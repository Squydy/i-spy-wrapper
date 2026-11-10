extends Node2D
class_name Stage
## Renders the original fixed-size stage (e.g. 640x480) into any window size.
## Children draw in stage coordinates; this node applies the scale + letterbox offset,
## so `get_local_mouse_position()` on any child yields stage-space coordinates.

signal fitted(scale_factor: float)

@export var stage_size: Vector2 = Vector2(640, 480)

var scale_factor: float = 1.0


func _ready() -> void:
	get_viewport().size_changed.connect(fit)
	Settings.changed.connect(fit)
	fit()


func set_stage_size(size: Vector2) -> void:
	stage_size = size
	fit()


func fit() -> void:
	var vp := get_viewport_rect().size
	if vp.x <= 0 or vp.y <= 0 or stage_size.x <= 0 or stage_size.y <= 0:
		return
	var s: float = minf(vp.x / stage_size.x, vp.y / stage_size.y)
	if Settings.scale_mode == "integer" and s >= 1.0:
		s = floorf(s)
	scale_factor = s
	scale = Vector2(s, s)
	position = ((vp - stage_size * s) * 0.5).floor()
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST if Settings.scale_mode == "integer" \
			else CanvasItem.TEXTURE_FILTER_LINEAR
	fitted.emit(s)


## Mouse position in stage coordinates.
func stage_mouse() -> Vector2:
	return get_local_mouse_position()


func contains(p: Vector2) -> bool:
	return Rect2(Vector2.ZERO, stage_size).has_point(p)


## Convert a window/viewport position to stage space (for input events).
func to_stage(viewport_pos: Vector2) -> Vector2:
	return (viewport_pos - position) / scale_factor
