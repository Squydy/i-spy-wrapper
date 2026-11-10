extends Control
## Library screen: lists installed packs from games/, launches them, and drives install/extract.

var list: ItemList
var detail_title: Label
var detail_info: RichTextLabel
var play_btn: Button
var extract_btn: Button
var install_btn: Button
var status: Label
var log_box: TextEdit
var file_dialog: FileDialog
var _selected: int = -1


func _ready() -> void:
	DisplayServer.window_set_title("I SPY Engine")
	set_anchors_preset(Control.PRESET_FULL_RECT)
	_build_ui()
	Library.rescanned.connect(_refresh)
	Installer.started.connect(_on_install_started)
	Installer.finished.connect(_on_install_finished)
	_refresh()
	# --play=<game id> jumps straight into a game (handy for testing / shortcuts)
	var play := Library.cmdline_option("play")
	if play != "" and not get_tree().root.has_meta("autoplayed"):
		get_tree().root.set_meta("autoplayed", true)
		var g := Library.get_game(play)
		if not g.is_empty() and g.get("extracted", false):
			get_tree().root.set_meta("launch_game", g)
			get_tree().change_scene_to_file.call_deferred("res://scenes/runtime.tscn")


func _build_ui() -> void:
	var bg := ColorRect.new()
	bg.color = Color(0.09, 0.1, 0.14)
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(bg)

	var margin := MarginContainer.new()
	margin.set_anchors_preset(Control.PRESET_FULL_RECT)
	for side in ["margin_left", "margin_right", "margin_top", "margin_bottom"]:
		margin.add_theme_constant_override(side, 32)
	add_child(margin)

	var root := VBoxContainer.new()
	root.add_theme_constant_override("separation", 16)
	margin.add_child(root)

	var header := HBoxContainer.new()
	root.add_child(header)
	var title := Label.new()
	title.text = "I SPY Engine"
	title.add_theme_font_size_override("font_size", 36)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(title)
	var opts := HBoxContainer.new()
	header.add_child(opts)
	var fs := Button.new()
	fs.text = "Fullscreen"
	fs.pressed.connect(Settings.toggle_fullscreen)
	opts.add_child(fs)
	var scale_btn := OptionButton.new()
	scale_btn.add_item("Smooth scaling")
	scale_btn.add_item("Integer scaling")
	scale_btn.selected = 1 if Settings.scale_mode == "integer" else 0
	scale_btn.item_selected.connect(func(i): Settings.set_scale_mode("integer" if i == 1 else "smooth"))
	opts.add_child(scale_btn)

	var body := HSplitContainer.new()
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	root.add_child(body)

	var left := VBoxContainer.new()
	left.custom_minimum_size.x = 360
	left.add_theme_constant_override("separation", 8)
	body.add_child(left)
	var lbl := Label.new()
	lbl.text = "Installed games"
	lbl.add_theme_font_size_override("font_size", 20)
	left.add_child(lbl)
	list = ItemList.new()
	list.size_flags_vertical = Control.SIZE_EXPAND_FILL
	list.add_theme_font_size_override("font_size", 18)
	list.item_selected.connect(_on_selected)
	list.item_activated.connect(func(_i): _play())
	left.add_child(list)
	var lbtns := HBoxContainer.new()
	left.add_child(lbtns)
	install_btn = Button.new()
	install_btn.text = "Install from ISO..."
	install_btn.pressed.connect(func(): file_dialog.popup_centered_ratio(0.7))
	lbtns.add_child(install_btn)
	var rescan := Button.new()
	rescan.text = "Rescan"
	rescan.pressed.connect(Library.rescan)
	lbtns.add_child(rescan)

	var right := VBoxContainer.new()
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	right.add_theme_constant_override("separation", 8)
	body.add_child(right)
	detail_title = Label.new()
	detail_title.add_theme_font_size_override("font_size", 28)
	right.add_child(detail_title)
	detail_info = RichTextLabel.new()
	detail_info.bbcode_enabled = true
	detail_info.fit_content = true
	detail_info.custom_minimum_size.y = 120
	right.add_child(detail_info)
	var rbtns := HBoxContainer.new()
	right.add_child(rbtns)
	play_btn = Button.new()
	play_btn.text = "Play"
	play_btn.add_theme_font_size_override("font_size", 22)
	play_btn.pressed.connect(_play)
	rbtns.add_child(play_btn)
	extract_btn = Button.new()
	extract_btn.text = "Re-extract assets"
	extract_btn.pressed.connect(_extract)
	rbtns.add_child(extract_btn)
	var logl := Label.new()
	logl.text = "Tool output"
	right.add_child(logl)
	log_box = TextEdit.new()
	log_box.editable = false
	log_box.size_flags_vertical = Control.SIZE_EXPAND_FILL
	right.add_child(log_box)

	status = Label.new()
	status.text = "Games folder: %s" % Library.games_root()
	root.add_child(status)

	file_dialog = FileDialog.new()
	file_dialog.access = FileDialog.ACCESS_FILESYSTEM
	file_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILES
	file_dialog.filters = PackedStringArray(["*.iso ; Disc images"])
	file_dialog.title = "Choose I SPY disc image(s)"
	file_dialog.files_selected.connect(_on_isos_chosen)
	add_child(file_dialog)


func _refresh() -> void:
	var prev := _selected
	list.clear()
	for g in Library.games:
		var flag := "" if g.get("extracted", false) else "  (needs extraction)"
		list.add_item("%s%s" % [g.get("title", g.get("id", "?")), flag])
	status.text = "Games folder: %s   -   %d installed" % [Library.games_root(), Library.games.size()]
	if Library.games.is_empty():
		detail_title.text = "No games installed"
		detail_info.text = "Use [b]Install from ISO...[/b] to add I SPY Treasure Hunt, Fantasy, Spooky Mansion Deluxe or Mystery.\nInstallation needs Python 3 on PATH (tools/ispytools)."
		play_btn.disabled = true
		extract_btn.disabled = true
		_selected = -1
		return
	_selected = clampi(prev, 0, Library.games.size() - 1)
	list.select(_selected)
	_on_selected(_selected)


func _on_selected(i: int) -> void:
	_selected = i
	var g: Dictionary = Library.games[i]
	detail_title.text = str(g.get("title", g.get("id")))
	var scenes: Dictionary = g.get("scenes", {}) if g.get("scenes") is Dictionary else {}
	var st: Dictionary = g.get("stage", {}) if g.get("stage") is Dictionary else {}
	detail_info.text = "[b]Director[/b] %s\n[b]Stage[/b] %sx%s\n[b]Source[/b] %s\n[b]Installed[/b] %s\n[b]Extracted[/b] %s%s\n[b]Path[/b] %s" % [
		str(g.get("director", "?")), str(st.get("width", "?")), str(st.get("height", "?")),
		str(g.get("source", {}).get("disc", "?")) if g.get("source") is Dictionary else "?",
		str(g.get("installedAt", "?")),
		"yes" if g.get("extracted", false) else "no",
		(" - %s screens" % str(scenes.get("count", "?"))) if g.get("extracted", false) else "",
		str(g.get("path", "")),
	]
	play_btn.disabled = not g.get("extracted", false) or Installer.busy
	extract_btn.disabled = Installer.busy
	extract_btn.text = "Re-extract assets" if g.get("extracted", false) else "Extract assets"


func _play() -> void:
	if _selected < 0 or _selected >= Library.games.size():
		return
	var g: Dictionary = Library.games[_selected]
	if not g.get("extracted", false):
		return
	get_tree().root.set_meta("launch_game", g)
	get_tree().change_scene_to_file("res://scenes/runtime.tscn")


func _extract() -> void:
	if _selected < 0:
		return
	Installer.extract_game(str(Library.games[_selected]["id"]))


func _on_isos_chosen(paths: PackedStringArray) -> void:
	for p in paths:
		# the installer runs one job at a time; queue sequentially
		while Installer.busy:
			await Installer.finished
		Installer.install_iso(p)


func _on_install_started(label: String) -> void:
	log_box.text = "%s...\nThis can take several minutes (bitmap decoding, audio/video conversion).\n" % label
	install_btn.disabled = true
	play_btn.disabled = true
	extract_btn.disabled = true


func _on_install_finished(ok: bool, output: String) -> void:
	log_box.text += output + ("\n\nDone." if ok else "\n\nFAILED - see output above.")
	log_box.scroll_vertical = log_box.get_line_count()
	install_btn.disabled = false
	_refresh()
