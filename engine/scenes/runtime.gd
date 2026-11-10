extends Control
## Game runtime root: black letterbox background, scaled Stage with the ScreenPlayer,
## and an overlay layer (toasts + Escape menu).

var game: Dictionary = {}

var stage: Stage
var player: ScreenPlayer
var overlay: CanvasLayer
var toast_label: Label
var menu: PanelContainer
var hunt_buttons: Array[Button] = []
var _toast_tween: Tween


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	var bg := ColorRect.new()
	bg.color = Color.BLACK
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(bg)

	stage = Stage.new()
	stage.name = "Stage"
	add_child(stage)
	player = ScreenPlayer.new()
	player.name = "ScreenPlayer"
	stage.add_child(player)
	player.toast.connect(show_toast)
	player.request_exit.connect(_exit_to_library)
	player.screen_changed.connect(func(id): DisplayServer.window_set_title("I SPY - %s - %s" % [game.get("title", ""), id]))

	_build_overlay()

	var g = get_tree().root.get_meta("launch_game", {})
	if g is Dictionary and not g.is_empty():
		start(g)
	elif not Library.games.is_empty():
		start(Library.games[0])
	else:
		_exit_to_library()


func start(manifest: Dictionary) -> void:
	game = manifest
	if not player.load_pack(manifest):
		show_toast("Could not load %s" % manifest.get("title", "game"))
		return
	stage.set_stage_size(player.stage_size())
	_refresh_menu()
	if not get_tree().root.has_meta("runtime_args_used"):
		get_tree().root.set_meta("runtime_args_used", true)
		var h := Library.cmdline_option("hunt")
		if h != "":
			player.set_hunt(h.to_upper())
		var s := Library.cmdline_option("screen")
		if s != "":
			player.go_to(s, false)


# ----------------------------------------------------------------------------- overlay
func _build_overlay() -> void:
	overlay = CanvasLayer.new()
	overlay.layer = 10
	add_child(overlay)

	toast_label = Label.new()
	toast_label.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	toast_label.anchor_left = 0.2
	toast_label.anchor_right = 0.8
	toast_label.offset_top = -80
	toast_label.offset_bottom = -40
	toast_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	toast_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	toast_label.add_theme_font_size_override("font_size", 22)
	toast_label.add_theme_color_override("font_outline_color", Color.BLACK)
	toast_label.add_theme_constant_override("outline_size", 6)
	toast_label.modulate.a = 0.0
	toast_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	overlay.add_child(toast_label)

	menu = PanelContainer.new()
	menu.set_anchors_preset(Control.PRESET_CENTER)
	menu.grow_horizontal = Control.GROW_DIRECTION_BOTH
	menu.grow_vertical = Control.GROW_DIRECTION_BOTH
	menu.visible = false
	overlay.add_child(menu)
	var margin := MarginContainer.new()
	for side in ["margin_left", "margin_right", "margin_top", "margin_bottom"]:
		margin.add_theme_constant_override(side, 24)
	menu.add_child(margin)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 10)
	margin.add_child(box)

	var title := Label.new()
	title.text = "Paused"
	title.add_theme_font_size_override("font_size", 26)
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	box.add_child(title)

	box.add_child(_menu_button("Resume", _toggle_menu))

	var hunts := HBoxContainer.new()
	hunts.alignment = BoxContainer.ALIGNMENT_CENTER
	var hl := Label.new()
	hl.text = "Hunt:"
	hunts.add_child(hl)
	for h in ["A", "B", "C"]:
		var b := Button.new()
		b.text = h
		b.toggle_mode = true
		b.pressed.connect(func(): player.set_hunt(h); _refresh_menu())
		hunts.add_child(b)
		hunt_buttons.append(b)
	box.add_child(hunts)

	box.add_child(_menu_button("Scale: smooth / integer", func():
		Settings.set_scale_mode("integer" if Settings.scale_mode == "smooth" else "smooth")
		_refresh_menu()))
	box.add_child(_menu_button("Toggle fullscreen (F11)", Settings.toggle_fullscreen))
	box.add_child(_menu_button("Show hotspots (F3)", func():
		Settings.debug_hotspots = not Settings.debug_hotspots
		Settings.save()
		Settings.apply()))
	box.add_child(_menu_button("Go to entry screen", func():
		player.go_to(str(player.index.get("entry", "")))
		_toggle_menu()))
	box.add_child(_menu_button("Reset progress for this game", func():
		Saves.reset()
		player.go_to(str(player.index.get("entry", "")), false)
		_toggle_menu()
		show_toast("Progress reset")))
	box.add_child(_menu_button("Back to library", _exit_to_library))


func _menu_button(text: String, cb: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.pressed.connect(cb)
	return b


func _refresh_menu() -> void:
	for b in hunt_buttons:
		b.button_pressed = (b.text == player.hunt)


func _toggle_menu() -> void:
	menu.visible = not menu.visible
	player.set_process_unhandled_input(not menu.visible)
	get_viewport().set_input_as_handled()


func show_toast(text: String) -> void:
	toast_label.text = text
	if _toast_tween:
		_toast_tween.kill()
	toast_label.modulate.a = 1.0
	_toast_tween = create_tween()
	_toast_tween.tween_interval(2.5)
	_toast_tween.tween_property(toast_label, "modulate:a", 0.0, 0.6)


func _exit_to_library() -> void:
	get_tree().root.set_meta("launch_game", {})
	get_tree().change_scene_to_file("res://scenes/launcher.tscn")


func _unhandled_key_input(event: InputEvent) -> void:
	if not event.is_pressed() or event.is_echo():
		return
	match event.keycode:
		KEY_ESCAPE:
			_toggle_menu()
		KEY_F11:
			Settings.toggle_fullscreen()
		KEY_F3:
			Settings.debug_hotspots = not Settings.debug_hotspots
			Settings.save()
			Settings.apply()
		KEY_BACKSPACE:
			if not menu.visible:
				player.go_back()
