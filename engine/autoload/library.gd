extends Node
## Scans the games/ directory for installed packs (games/<id>/manifest.json).

signal rescanned

## Array of manifests (Dictionary) with an extra "path" key (absolute pack directory).
var games: Array[Dictionary] = []


func _ready() -> void:
	rescan()


## Value of a `--name=value` command line option (before or after the `--` separator), or "".
static func cmdline_option(name: String) -> String:
	var prefix := "--%s=" % name
	var all: PackedStringArray = OS.get_cmdline_args()
	all.append_array(OS.get_cmdline_user_args())
	for arg in all:
		if arg.begins_with(prefix):
			return arg.substr(prefix.length())
	return ""


## Absolute path to the games root. Resolution order:
## settings override -> --games=<path> command line -> <repo>/games (editor) -> <exe dir>/games.
func games_root() -> String:
	if Settings.games_root_override != "":
		return Settings.games_root_override
	var opt := cmdline_option("games")
	if opt != "":
		return opt
	return repo_root().path_join("games")


## Directory that holds engine/, tools/ and games/.
func repo_root() -> String:
	if OS.has_feature("editor"):
		return ProjectSettings.globalize_path("res://").path_join("..").simplify_path()
	var exe_dir := OS.get_executable_path().get_base_dir()
	for cand in [exe_dir, exe_dir.path_join("..").simplify_path()]:
		if DirAccess.dir_exists_absolute(cand.path_join("games")) or DirAccess.dir_exists_absolute(cand.path_join("tools")):
			return cand
	return exe_dir


func tools_root() -> String:
	return repo_root().path_join("tools")


func rescan() -> void:
	games.clear()
	var root := games_root()
	if DirAccess.dir_exists_absolute(root):
		for d in DirAccess.get_directories_at(root):
			var pack := root.path_join(d)
			var manifest = load_json(pack.path_join("manifest.json"))
			if manifest is Dictionary and manifest.has("id"):
				manifest["path"] = pack
				games.append(manifest)
	games.sort_custom(func(a, b): return str(a.get("title", "")) < str(b.get("title", "")))
	rescanned.emit()


func get_game(id: String) -> Dictionary:
	for g in games:
		if g.get("id", "") == id:
			return g
	return {}


static func load_json(path: String) -> Variant:
	if not FileAccess.file_exists(path):
		return null
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		return null
	var text := f.get_as_text()
	f.close()
	var json := JSON.new()
	if json.parse(text) != OK:
		push_warning("JSON parse error in %s: %s" % [path, json.get_error_message()])
		return null
	return json.data
