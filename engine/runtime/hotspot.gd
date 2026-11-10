class_name Hotspot
extends RefCounted
## A clickable region in stage coordinates. Optionally alpha-tested against an image
## (Director "matte" ink), so irregular objects only react on their opaque pixels.

var id: String = ""
var rect: Rect2
var image: String = ""      # pack-relative image for alpha test (empty = plain rect)
var enabled: bool = true
var cursor: int = DisplayServer.CURSOR_POINTING_HAND
var on_click: Callable
var on_enter: Callable
var on_exit: Callable
var hovered: bool = false
var tag: Variant = null     # adapter-defined payload


func _init(p_id: String, p_rect: Rect2, p_image: String = "") -> void:
	id = p_id
	rect = p_rect
	image = p_image


func hit(p: Vector2) -> bool:
	if not enabled or not rect.has_point(p):
		return false
	if image == "":
		return true
	var img := Assets.image(image)
	if img == null:
		return true
	var local := (p - rect.position).floor()
	if local.x < 0 or local.y < 0 or local.x >= img.get_width() or local.y >= img.get_height():
		return false
	return img.get_pixelv(Vector2i(local)).a > 0.05


static func rect_from(a: Variant) -> Rect2:
	if a is Array and a.size() == 4:
		return Rect2(a[0], a[1], a[2] - a[0], a[3] - a[1])
	return Rect2()
